from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Security, WebSocket
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging
from urllib.parse import unquote
import asyncio
import json

from app.database.database import get_db
from app.schemas.deployment_models import (
    DeploymentConfig, 
    DeploymentRequest, 
    Deployment, 
    DeploymentResult,
    DeploymentStatus,
    DeploymentEnvironment
)
from app.database.deployment_crud import (
    create_deployment_config,
    get_deployment_config,
    update_deployment_config,
    delete_deployment_config,
    list_deployment_configs,
    get_deployment,
    list_deployments
)
from app.deployment.engine import (
    start_deployment,
    cancel_deployment,
    get_deployment_status,
    active_deployments
)
from app.routes.auth import get_current_user, verify_token

logger = logging.getLogger(__name__)
router = APIRouter()


# Deployment Configuration Endpoints
@router.post(
    "/configs", 
    response_model=Dict[str, Any],
    summary="Create a new deployment configuration",
    description="""
    Creates a new deployment configuration for a specified repository.
    
    The configuration includes:
    - Repository information (ID and full name)
    - Deployment branch (which branch to deploy from)
    - Auto-deployment settings (whether to deploy automatically on push)
    - Deploy command (shell script to execute)
    - Environment variables (optional key-value pairs for deployment)
    
    Example without environment variables:
    ```json
    {
      "repo_id": 12345678,
      "repo_full_name": "username/docker-app",
      "branch": "main",
      "auto_deploy": true,
      "deploy_command": "./deploy.sh"
    }
    ```
    
    Example with environment variables:
    ```json
    {
      "repo_id": 12345678,
      "repo_full_name": "username/docker-app",
      "branch": "main",
      "auto_deploy": true,
      "deploy_command": "./deploy.sh",
      "environment_variables": {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
        "REDIS_URL": "redis://localhost:6379",
        "API_KEY": "your-api-key",
        "NODE_ENV": "production",
        "PORT": "3000",
        "DEBUG": "false"
      }
    }
    ```
    
    The environment variables will be:
    1. Added to the deployment process environment
    2. Written to a .env file in the repository root
    
    This configuration will be used when deployments are triggered manually or automatically through webhooks.
    """,
    responses={
        200: {
            "description": "Deployment configuration created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "8f9e26c5-3e3b-4c12-91f5-23e1d5c3b504",
                        "repo_full_name": "username/docker-app",
                        "message": "Deployment configuration created successfully"
                    }
                }
            }
        },
        400: {"description": "Configuration already exists for this repository"},
        401: {"description": "Authentication required"}
    }
)
async def create_config(
    config: DeploymentConfig,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new deployment configuration for a repository"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Check if config already exists
    existing_config = get_deployment_config(db, config.repo_full_name, current_user["id"])
    if existing_config:
        raise HTTPException(status_code=400, detail="Deployment configuration already exists for this repository")
    
    # Create new config
    db_config = create_deployment_config(db, current_user["id"], config)
    return {
        "id": db_config.id,
        "repo_full_name": db_config.repo_full_name,
        "message": "Deployment configuration created successfully"
    }


@router.get(
    "/configs",
    response_model=List[Dict[str, Any]],
    summary="List deployment configurations",
    description="""
    Retrieves a list of deployment configurations for repositories.
    
    Results are paginated and show configurations for repositories the authenticated user has access to.
    
    Example response:
    ```json
    [
      {
        "id": "7a8b9c0d-1e2f-3g4h-5i6j-7k8l9m0n1o2p",
        "repo_id": 12345678,
        "repo_full_name": "username/docker-app",
        "branch": "main",
        "auto_deploy": true,
        "deploy_command": "./deploy.sh"
      },
      {
        "id": "3p4o5n6m-7l8k-9j0i-1h2g-3f4e5d6c7b8a",
        "repo_id": 87654321,
        "repo_full_name": "username/api-service",
        "branch": "develop",
        "auto_deploy": true,
        "deploy_command": "./api-deploy.sh"
      }
    ]
    ```
    
    Use the `limit` and `offset` query parameters for pagination.
    """,
    responses={
        200: {
            "description": "List of deployment configurations",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "7a8b9c0d-1e2f-3g4h-5i6j-7k8l9m0n1o2p",
                            "repo_id": 12345678,
                            "repo_full_name": "username/docker-app",
                            "branch": "main",
                            "auto_deploy": True,
                            "deploy_command": "./deploy.sh"
                        }
                    ]
                }
            }
        },
        401: {"description": "Authentication required"}
    }
)
async def get_configs(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all deployment configurations for the current user"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    configs = list_deployment_configs(db, current_user["id"])
    return [
        {
            "id": config.id,
            "repo_id": config.repo_id,
            "repo_full_name": config.repo_full_name,
            "branch": config.branch,
            "auto_deploy": config.auto_deploy,
            "deploy_command": config.deploy_command,
            "created_at": config.created_at,
            "updated_at": config.updated_at
        }
        for config in configs
    ]


@router.get(
    "/configs/{repo_owner}/{repo_name}", 
    response_model=Dict[str, Any],
    summary="Get deployment configuration for a repository",
    description="""
    Retrieves the deployment configuration for a specific repository.
    
    The repository is identified by its owner and name.
    Returns complete configuration details for the specified repository.
    """,
    responses={
        200: {
            "description": "Deployment configuration",
            "content": {
                "application/json": {
                    "example": {
                        "id": "8f9e26c5-3e3b-4c12-91f5-23e1d5c3b504",
                        "repo_id": 98765,
                        "repo_full_name": "username/docker-app",
                        "branch": "main",
                        "auto_deploy": True,
                        "deploy_command": "./deploy.sh",
                        "created_at": "2023-03-28T12:00:00Z",
                        "updated_at": "2023-03-28T12:00:00Z"
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        404: {"description": "Configuration not found"}
    }
)
async def get_config(
    repo_owner: str,
    repo_name: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get deployment configuration for a repository"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Combine owner and name to get full repository name
    repo_full_name = f"{repo_owner}/{repo_name}"
    
    config = get_deployment_config(db, repo_full_name, current_user["id"])
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    return {
        "id": config.id,
        "repo_id": config.repo_id,
        "repo_full_name": config.repo_full_name,
        "branch": config.branch,
        "auto_deploy": config.auto_deploy,
        "deploy_command": config.deploy_command,
        "created_at": config.created_at,
        "updated_at": config.updated_at
    }


@router.patch(
    "/configs/{config_id}", 
    response_model=Dict[str, Any],
    summary="Update a deployment configuration",
    description="""
    Updates an existing deployment configuration.
    
    Allows partial updates of configuration fields. Only the fields included in the request will be updated.
    
    Example request:
    ```json
    {
      "branch": "develop",
      "auto_deploy": false,
      "deploy_command": "./api-deploy.sh"
    }
    ```
    
    This will only update the specified fields, leaving other configuration values unchanged.
    """,
    responses={
        200: {
            "description": "Deployment configuration updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "8f9e26c5-3e3b-4c12-91f5-23e1d5c3b504",
                        "repo_full_name": "username/docker-app",
                        "message": "Deployment configuration updated successfully"
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        404: {"description": "Configuration not found"}
    }
)
async def update_config(
    config_id: str,
    config_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update a deployment configuration"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    updated_config = update_deployment_config(db, config_id, config_data)
    if not updated_config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    return {
        "id": updated_config.id,
        "repo_full_name": updated_config.repo_full_name,
        "message": "Deployment configuration updated successfully"
    }


@router.delete(
    "/configs/{config_id}",
    response_model=Dict[str, Any],
    summary="Delete a deployment configuration",
    description="""
    Deletes an existing deployment configuration.
    
    The configuration is identified by its ID.
    Only the owner of the configuration can delete it.
    """,
    responses={
        200: {
            "description": "Configuration deleted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Configuration deleted successfully"
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        403: {"description": "Not authorized to delete this configuration"},
        404: {"description": "Configuration not found"}
    }
)
async def delete_config(
    config_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a deployment configuration"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Try to delete the config
    success = delete_deployment_config(db, config_id, current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    return {"message": "Configuration deleted successfully"}


# Deployment Endpoints
@router.post(
    "/trigger",
    response_model=Dict[str, Any],
    summary="Manually trigger a deployment",
    description="""
    Manually triggers a deployment for a specific repository and branch.
    
    A deployment configuration must exist for the repository. The branch specified should
    match the branch configured in the deployment settings.
    
    Example request:
    ```json
    {
      "repo_full_name": "username/docker-app",
      "branch": "main",
      "commit_sha": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
    }
    ```
    
    Response for a successful trigger:
    ```json
    {
      "status": "success",
      "message": "Deployment triggered successfully",
      "deployment_id": "7a8b9c0d-1e2f-3g4h-5i6j-7k8l9m0n1o2p",
      "repo_full_name": "username/docker-app",
      "branch": "main"
    }
    ```
    
    The deployment process will:
    1. Clone the repository and checkout the specified commit
    2. Execute the deploy command script
    """,
    responses={
        200: {
            "description": "Deployment triggered successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Deployment triggered successfully",
                        "deployment_id": "7a8b9c0d-1e2f-3g4h-5i6j-7k8l9m0n1o2p",
                        "repo_full_name": "username/docker-app",
                        "branch": "main"
                    }
                }
            }
        },
        400: {
            "description": "Invalid request",
            "content": {
                "application/json": {
                    "examples": {
                        "missing_config": {
                            "summary": "No configuration found",
                            "value": {
                                "status": "error",
                                "message": "No deployment configuration found for this repository"
                            }
                        }
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        403: {"description": "Not authorized to deploy this repository"},
        500: {
            "description": "Server error",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Failed to trigger deployment due to server error"
                    }
                }
            }
        }
    }
)
async def trigger_deployment(
    request: DeploymentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Trigger a new deployment"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Check if repository has a deployment configuration
    config = get_deployment_config(db, request.repo_full_name, current_user["id"])
    if not config:
        raise HTTPException(
            status_code=404, 
            detail="No deployment configuration found for this repository"
        )
    
    # Set username for triggered_by field if not provided
    if not request.triggered_by:
        request.triggered_by = current_user.get("username", "unknown")
    
    # Set manual trigger flag
    request.manual_trigger = True
    
    # Start deployment
    success, message, deployment_id = start_deployment(db, current_user["id"], request)
    
    if not success or not deployment_id:
        raise HTTPException(status_code=500, detail=message)
    
    # Return as dictionary instead of DeploymentResult object
    return {
        "deployment_id": deployment_id,
        "status": DeploymentStatus.PENDING.value,
        "message": "Deployment started successfully",
        "logs_url": f"/deployments/{deployment_id}/logs"
    }


@router.get(
    "/deployments", 
    response_model=List[Dict[str, Any]],
    summary="List deployments",
    description="""
    Retrieves a list of deployments with optional filtering by repository.
    
    Results are paginated and ordered by creation date (newest first).
    
    Example response:
    ```json
    [
      {
        "id": "72b3d27c-5abe-4f7b-9c9d-345ea1c45f21",
        "repo_full_name": "username/docker-app",
        "commit_sha": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
        "branch": "main",
        "status": "completed",
        "created_at": "2023-03-28T15:05:00Z",
        "started_at": "2023-03-28T15:05:01Z",
        "completed_at": "2023-03-28T15:08:30Z",
        "triggered_by": "github-webhook",
        "manual_trigger": false
      },
      {
        "id": "98a7b6c5-4d3e-2f1g-0h9i-8j7k6l5m4n3o",
        "repo_full_name": "username/docker-app",
        "commit_sha": "b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8",
        "branch": "feature/new-ui",
        "status": "failed",
        "created_at": "2023-03-27T10:15:00Z",
        "started_at": "2023-03-27T10:15:05Z",
        "completed_at": "2023-03-27T10:18:20Z",
        "triggered_by": "username",
        "manual_trigger": true
      },
      {
        "id": "54f3e2d1-c0b9-a8b7-6c5d-4e3f2g1h0i9j",
        "repo_full_name": "username/api-service",
        "commit_sha": "c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9",
        "branch": "main",
        "status": "in_progress",
        "created_at": "2023-03-28T16:30:00Z",
        "started_at": "2023-03-28T16:30:10Z",
        "completed_at": null,
        "triggered_by": "github-webhook",
        "manual_trigger": false
      }
    ]
    ```
    
    Use the query parameters to filter and paginate results:
    - `repo_full_name`: Filter by repository name (e.g., `username/docker-app`)
    - `limit`: Number of results per page (default: 10, max: 100)
    - `offset`: Number of results to skip (for pagination)
    """,
    responses={
        200: {
            "description": "List of deployments",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "72b3d27c-5abe-4f7b-9c9d-345ea1c45f21",
                            "repo_full_name": "username/docker-app",
                            "commit_sha": "a1b2c3d4e5f6g7h8i9j0",
                            "branch": "main",
                            "status": "completed",
                            "created_at": "2023-03-28T12:05:00Z",
                            "started_at": "2023-03-28T12:05:01Z",
                            "completed_at": "2023-03-28T12:06:30Z",
                            "triggered_by": "username",
                            "manual_trigger": True
                        }
                    ]
                }
            }
        },
        401: {"description": "Authentication required"}
    }
)
async def get_deployments(
    repo_full_name: Optional[str] = None,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List deployments with optional filtering"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    deployments = list_deployments(
        db, 
        repo_full_name=repo_full_name, 
        user_id=current_user["id"], 
        limit=limit, 
        offset=offset
    )
    
    return [
        {
            "id": deployment.id,
            "repo_full_name": deployment.repo_full_name,
            "commit_sha": deployment.commit_sha,
            "branch": deployment.branch,
            "status": deployment.status,
            "created_at": deployment.created_at,
            "started_at": deployment.started_at,
            "completed_at": deployment.completed_at,
            "triggered_by": deployment.triggered_by,
            "manual_trigger": deployment.manual_trigger
        }
        for deployment in deployments
    ]


@router.get(
    "/deployments/{deployment_id}", 
    response_model=Dict[str, Any],
    summary="Get deployment details",
    description="""
    Retrieves detailed information about a specific deployment.
    
    Includes status, timing information, and error messages if any.
    
    Example response:
    ```json
    {
      "id": "72b3d27c-5abe-4f7b-9c9d-345ea1c45f21",
      "repo_full_name": "username/docker-app",
      "commit_sha": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
      "branch": "main",
      "status": "completed",
      "created_at": "2023-03-28T12:05:00Z",
      "started_at": "2023-03-28T12:05:01Z",
      "completed_at": "2023-03-28T12:06:30Z",
      "triggered_by": "username",
      "manual_trigger": true,
      "error_message": null
    }
    ```
    
    The possible status values are:
    - `pending`: Deployment is queued but not started
    - `in_progress`: Deployment is currently running
    - `completed`: Deployment finished successfully
    - `failed`: Deployment failed with errors
    - `cancelled`: Deployment was manually cancelled
    """,
    responses={
        200: {
            "description": "Deployment details",
            "content": {
                "application/json": {
                    "example": {
                        "id": "72b3d27c-5abe-4f7b-9c9d-345ea1c45f21",
                        "repo_full_name": "username/docker-app",
                        "commit_sha": "a1b2c3d4e5f6g7h8i9j0",
                        "branch": "main",
                        "status": "completed",
                        "created_at": "2023-03-28T12:05:00Z",
                        "started_at": "2023-03-28T12:05:01Z",
                        "completed_at": "2023-03-28T12:06:30Z",
                        "triggered_by": "username",
                        "manual_trigger": True,
                        "error_message": None
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        403: {"description": "Not authorized to access this deployment"},
        404: {"description": "Deployment not found"}
    }
)
async def get_deployment_details(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get details of a specific deployment"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    deployment = get_deployment(db, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Check if user owns this deployment
    if deployment.user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this deployment")
    
    return {
        "id": deployment.id,
        "repo_full_name": deployment.repo_full_name,
        "commit_sha": deployment.commit_sha,
        "branch": deployment.branch,
        "status": deployment.status,
        "created_at": deployment.created_at,
        "started_at": deployment.started_at,
        "completed_at": deployment.completed_at,
        "triggered_by": deployment.triggered_by,
        "manual_trigger": deployment.manual_trigger,
        "error_message": deployment.error_message
    }


@router.get(
    "/deployments/{deployment_id}/logs", 
    response_model=Dict[str, Any],
    summary="Get deployment logs",
    description="""
    Retrieves the logs for a specific deployment.
    
    Logs include all output from the deploy command script.
    
    Example response:
    ```json
    {
      "deployment_id": "72b3d27c-5abe-4f7b-9c9d-345ea1c45f21",
      "repo_full_name": "username/docker-app",
      "status": "completed",
      "logs": [
        "[2023-03-28T12:05:01Z] Starting deployment of username/docker-app at commit a1b2c3d4e5f6",
        "[2023-03-28T12:05:02Z] Preparing deployment directory",
        "[2023-03-28T12:05:10Z] Running: ./deploy.sh",
        "[2023-03-28T12:05:15Z] Building Docker image for commit a1b2c3d4e5f6",
        "[2023-03-28T12:05:45Z] Docker build completed successfully",
        "[2023-03-28T12:05:50Z] Stopping previous container",
        "[2023-03-28T12:06:00Z] Starting new container",
        "[2023-03-28T12:06:15Z] Running health checks",
        "[2023-03-28T12:06:25Z] Deployment completed successfully"
      ]
    }
    ```
    """,
    responses={
        200: {
            "description": "Deployment logs",
            "content": {
                "application/json": {
                    "example": {
                        "deployment_id": "72b3d27c-5abe-4f7b-9c9d-345ea1c45f21",
                        "repo_full_name": "username/docker-app",
                        "status": "completed",
                        "logs": [
                            "[2023-03-28T12:05:01Z] Starting deployment of username/docker-app at commit a1b2c3d4e5f6",
                            "[2023-03-28T12:05:10Z] Running: ./deploy.sh",
                            "[2023-03-28T12:06:25Z] Deployment completed successfully"
                        ]
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        403: {"description": "Not authorized to access this deployment"},
        404: {"description": "Deployment not found"}
    }
)
async def get_deployment_logs(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get logs for a specific deployment"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    deployment = get_deployment(db, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Check if user owns this deployment
    if deployment.user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this deployment")
    
    return {
        "deployment_id": deployment.id,
        "repo_full_name": deployment.repo_full_name,
        "status": deployment.status,
        "logs": deployment.logs
    }


@router.post(
    "/deployments/{deployment_id}/cancel", 
    response_model=Dict[str, Any],
    summary="Cancel a deployment",
    description="""
    Cancels a running deployment.
    
    Only deployments with 'pending' or 'in_progress' status can be cancelled.
    
    Example response:
    ```json
    {
      "message": "Deployment cancelled successfully"
    }
    ```
    
    The deployment will be marked as 'cancelled' and any running processes will be terminated.
    Temporary resources created for the deployment will be cleaned up.
    """,
    responses={
        200: {
            "description": "Deployment cancelled successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Deployment cancelled successfully"
                    }
                }
            }
        },
        400: {"description": "Cannot cancel deployment with current status"},
        401: {"description": "Authentication required"},
        403: {"description": "Not authorized to cancel this deployment"},
        404: {"description": "Deployment not found"},
        500: {"description": "Failed to cancel deployment"}
    }
)
async def cancel_deployment_request(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Cancel a running deployment"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    deployment = get_deployment(db, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Check if user owns this deployment
    if deployment.user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this deployment")
    
    # Check if deployment can be cancelled
    if deployment.status not in [DeploymentStatus.PENDING.value, DeploymentStatus.IN_PROGRESS.value]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel deployment with status '{deployment.status}'"
        )
    
    success = cancel_deployment(db, deployment_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel deployment")
    
    return {"message": "Deployment cancelled successfully"}


@router.websocket("/deployments/{deployment_id}/logs")
async def deployment_logs(websocket: WebSocket, deployment_id: str, token: str):
    """Stream deployment logs in real-time via WebSocket"""
    try:
        # Verify token
        user = verify_token(token)
        if not user:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        await websocket.accept()
        
        # Send initial logs
        db = next(get_db())
        deployment = get_deployment(db, deployment_id)
        if not deployment:
            await websocket.close(code=4004, reason="Deployment not found")
            return
            
        # Send existing logs
        if deployment.logs:
            for log in deployment.logs:
                await websocket.send_text(json.dumps({
                    "type": "log",
                    "data": log
                }))
        
        # Stream new logs
        last_log_count = len(deployment.logs or [])
        while True:
            # Check if deployment is still active
            if deployment_id not in active_deployments:
                # Send final status
                deployment = get_deployment(db, deployment_id)
                if deployment:
                    await websocket.send_text(json.dumps({
                        "type": "status",
                        "data": deployment.status
                    }))
                await websocket.close()
                break
            
            # Get fresh deployment data
            deployment = get_deployment(db, deployment_id)
            if not deployment:
                await websocket.close()
                break
                
            # Send new logs
            current_logs = deployment.logs or []
            if len(current_logs) > last_log_count:
                new_logs = current_logs[last_log_count:]
                for log in new_logs:
                    await websocket.send_text(json.dumps({
                        "type": "log",
                        "data": log
                    }))
                last_log_count = len(current_logs)
            
            # Send current status
            await websocket.send_text(json.dumps({
                "type": "status",
                "data": deployment.status
            }))
            
            await asyncio.sleep(1)  # Poll every second
            
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        try:
            await websocket.close()
        except:
            pass 