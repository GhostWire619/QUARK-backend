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
from app.settings import WEBHOOK_URL
from fastapi.security import OAuth2PasswordBearer
from app.utils.webhook_utils import (
    create_webhook,
    check_existing_webhook)

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
    logger.info(f"Setting up webhook for {repo_full_name} to {WEBHOOK_URL}")
    
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
                    hook_url=WEBHOOK_URL,
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
    "/webhook",
    summary="Receive GitHub Webhook Events",
    response_model=Dict[str, str],
    responses={
        200: {
            "description": "Successfully processed webhook event",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "event_id": "2024-03-28T12:00:00-push"
                    }
                }
            }
        },
        400: {"description": "Missing required headers"},
        500: {"description": "Error processing webhook event"}
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
        
        add_webhook_event(db_session, event_id, event_type, payload)
            
        return {"status": "success", "event_id": event_id}
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))