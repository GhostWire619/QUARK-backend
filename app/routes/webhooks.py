from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks, status
from sqlalchemy.orm import Session
import logging
from datetime import datetime
import httpx
from typing import List, Dict, Any

from app.database.database import get_db
from app.database.webhook_crud import (
    add_webhook_event,
    add_or_update_registered_webhook
)
from app.settings import settings
from fastapi.security import OAuth2PasswordBearer
from app.utils.webhook_utils import (
    create_webhook,
    check_existing_webhook)
from app.deployment.engine import process_webhook_event

router = APIRouter()
logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
    
@router.get(
    "/repos/{owner}/{repo}/commits",
    summary="Get Repository Commits",
    response_model=List[Dict[str, Any]],
    responses={
        200: {
            "description": "Successfully retrieved repository commits with detailed information",
            "content": {
                "application/json": {
                    "example": [{
                        "sha": "commit_sha",
                        "commit": {
                            "message": "commit message",
                            "author": {"name": "author name", "date": "commit date"}
                        },
                        "stats": {"additions": 0, "deletions": 0, "total": 0}
                    }]
                }
            }
        },
        401: {"description": "Not authenticated"},
        404: {"description": "Repository not found"}
    }
)
async def get_repo_commits(
    owner: str,
    repo: str,
    token: str = Depends(oauth2_scheme)
):
    """
    Retrieves detailed commit information for a specific repository.
    
    This endpoint:
    1. Fetches the last 100 commits from the repository
    2. For each commit, retrieves detailed information including stats
    3. Returns comprehensive commit data including changes and author details
    
    Args:
        owner (str): Repository owner username
        repo (str): Repository name
        token (str): GitHub access token
    
    Returns:
        List[Dict]: List of detailed commit information
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/commits",
                headers={"Authorization": f"Bearer {token}"},
                params={"page": 1 , "per_page":100}
            )
            
            if response.status_code == 200:
                commits = response.json()
                # Fetch additional details for each commit
                detailed_commits = []
                for commit in commits:
                    commit_sha = commit['sha']
                    details_response = await client.get(
                        f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}",
                        headers={"Authorization": f"Bearer {token}"}
                    )
                    if details_response.status_code == 200:
                        detailed_commits.append(details_response.json())
                return detailed_commits
            else:
                logger.error(f"GitHub API error: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
    
    except Exception as e:
        logger.error(f"Error fetching repo commits: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/repos/{owner}/{repo}/setup-webhook",
    summary="Set Up Repository Webhook",
    response_model=Dict[str, str],
    responses={
        200: {
            "description": "Webhook setup successful",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Webhook created successfully",
                        "hook_id": "12345"
                    }
                }
            }
        },
        401: {"description": "Not authenticated"},
        404: {"description": "Repository not found"},
        500: {"description": "Server error during webhook setup"}
    }
)
async def setup_webhook(
    background_tasks: BackgroundTasks,
    owner: str,
    repo: str,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db)
):
    """
    Sets up a webhook for a GitHub repository.
    
    This endpoint:
    1. Checks if a webhook already exists for the repository
    2. If exists, updates the database record
    3. If not, creates a new webhook and stores it in the database
    
    The webhook will be configured to send the following events:
    - Push events
    - Pull request events
    - Issue events
    
    Args:
        owner (str): Repository owner username
        repo (str): Repository name
        token (str): GitHub access token
        db_session (Session): Database session
    
    Returns:
        Dict[str, str]: Status of webhook setup operation
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    repo_full_name = f"{owner}/{repo}"
    logger.info(f"Setting up webhook for {repo_full_name} to {settings.WEBHOOK_URL}")
    
    try:
        async with httpx.AsyncClient() as client:
            existing_hook = await check_existing_webhook(client, owner,repo,token)
            if existing_hook:
                hook_id = str(existing_hook['id'])
                hook_url = existing_hook['config'].get('url', '')
                events = existing_hook.get('events', [])
                
                add_or_update_registered_webhook(
                    db_session,
                    repository=repo_full_name,
                    hook_id=hook_id,
                    hook_url=hook_url,
                    events=events
                )
                
                logger.info(f"Webhook already exists for {repo_full_name}: {hook_id}")
                return {
                    "status": "success", 
                    "message": "Webhook already exists", 
                    "hook_id": hook_id
                }
            
            hook_data = await create_webhook(client, owner,repo,token)
            if hook_data:
                hook_id = str(hook_data['id'])
                events = hook_data.get('events', [])
                
                add_or_update_registered_webhook(
                    db_session,
                    repository=repo_full_name,
                    hook_id=hook_id,
                    hook_url=settings.WEBHOOK_URL,
                    events=events
                )
                
                logger.info(f"Webhook created successfully: {hook_id}")
                
                return {"status": "success", "message": "Webhook created successfully", "hook_id": hook_id}
            else:
                return {"status": "error", "message": "Failed to create webhook"}
    
    except Exception as e:
        logger.error(f"Error setting up webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/github",
    summary="Process GitHub webhook events",
    description="""
    Handles webhook events from GitHub repositories.
    
    This endpoint processes push events to trigger deployments if applicable.
    Repository must have a deployment configuration with auto-deploy enabled for the branch that received a push.
    
    Example webhook payload from GitHub (push event):
    ```json
    {
      "ref": "refs/heads/main",
      "repository": {
        "id": 123456789,
        "full_name": "username/docker-app",
        "name": "docker-app",
        "owner": {
          "login": "username",
          "id": 12345
        }
      },
      "pusher": {
        "name": "username",
        "email": "user@example.com"
      },
      "head_commit": {
        "id": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9",
        "message": "Update Dockerfile and deployment script",
        "timestamp": "2023-03-28T15:00:00Z",
        "author": {
          "name": "Username",
          "email": "user@example.com"
        }
      }
    }
    ```
    
    Response example for a successful webhook processing:
    ```json
    {
      "status": "success",
      "message": "Webhook event processed",
      "action": "Deployment triggered for docker-app/main",
      "deployment_id": "7a8b9c0d-1e2f-3g4h-5i6j-7k8l9m0n1o2p"
    }
    ```
    
    Or when no deployment is triggered:
    ```json
    {
      "status": "success",
      "message": "Webhook event processed",
      "action": "No deployment triggered: Auto-deploy not enabled for this branch"
    }
    ```
    
    Note: This endpoint must be added as a webhook in your GitHub repository settings with the content type set to 'application/json'.
    """,
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Webhook processed successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "deployment_triggered": {
                            "summary": "Deployment triggered",
                            "value": {
                                "status": "success",
                                "message": "Webhook event processed",
                                "action": "Deployment triggered for username/docker-app:main",
                                "deployment_id": "7a8b9c0d-1e2f-3g4h-5i6j-7k8l9m0n1o2p"
                            }
                        },
                        "no_deployment": {
                            "summary": "No deployment triggered",
                            "value": {
                                "status": "success",
                                "message": "Webhook event processed",
                                "action": "No deployment triggered: Auto-deploy not enabled for this branch"
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Invalid webhook payload",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Invalid webhook payload: Missing required fields"
                    }
                }
            }
        },
        500: {
            "description": "Server error",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Failed to process webhook"
                    }
                }
            }
        }
    }
)
async def webhook(
    request: Request,
    db_session: Session = Depends(get_db)
):
    """
    Receives and processes GitHub webhook events.
    
    This endpoint:
    1. Validates the webhook event type
    2. Processes the payload
    3. Stores the event in the database
    4. Triggers automatic deployments if configured
    
    Supported event types:
    - push
    - pull_request
    - issues
    - issue_comment
    - and more...
    
    Args:
        request (Request): The incoming webhook request
        db_session (Session): Database session
    
    Returns:
        Dict[str, str]: Status of webhook processing
    """
    try:
        event_type = request.headers.get("X-GitHub-Event")
        if not event_type:
            raise HTTPException(status_code=400, detail="X-GitHub-Event header missing")
            
        payload = await request.json()
        repository = payload.get("repository", {})
        repo_name = repository.get("full_name", "unknown")
        
        logger.info(f"Received {event_type} event from {repo_name}")
        
        event_id = f"{datetime.now().isoformat()}-{event_type}"
        timestamp = datetime.now().isoformat()
        
        # Store webhook event
        add_webhook_event(db_session, event_id, event_type, payload)
        
        # Check if this event should trigger a deployment
        deployment_id = None
        deployment_triggered = False
        
        if event_type == "push":
            # Only process main branch push events for deployment
            ref = payload.get("ref", "")
            if ref:
                # Process webhook for deployment
                deployment_id = process_webhook_event(db_session, event_type, payload)
                if deployment_id:
                    deployment_triggered = True
                    logger.info(f"Triggered deployment {deployment_id} for {repo_name}")
            
        return {
            "status": "success", 
            "event_id": event_id,
            "deployment_triggered": deployment_triggered,
            "deployment_id": deployment_id
        }
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))