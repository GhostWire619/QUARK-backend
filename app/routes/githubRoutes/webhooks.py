from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks, status
from fastapi.responses import JSONResponse
from typing import Dict, Any, List
import logging
from datetime import datetime
from git import Repo
import httpx
import os
import asyncio


from app.database.webhook_db import (get_db,
    add_webhook_event,
    add_or_update_registered_webhook
)
from app.schemas.models import (WebhookPayload, WebhookEvent, RegisteredWebhook,AuthCallbackInput,UserProfileInput,UserReposInput,RepoCommitsInput,SetupWebhookInput,WebhookInput)
from app.settings import WEBHOOK_URL, WEBHOOK_SECRET, REPOS_FOLDER
from fastapi.security import OAuth2PasswordBearer

from app.utils.webhook_utils import (process_push_event,sync_all_webhooks,sync_repository_webhooks)

router = APIRouter()
logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

@router.get("/user/repos")
async def get_user_repos(input: UserReposInput = Depends(oauth2_scheme)):
    """
    Get GitHub user repositories
    """
    if not input.token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user/repos?sort=updated&per_page=100",
                headers={"Authorization": f"Bearer {input.token}"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"GitHub API error: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
    
    except Exception as e:
        logger.error(f"Error fetching user repositories: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/repos/{owner}/{repo}/commits")
async def get_repo_commits(input: RepoCommitsInput = Depends(oauth2_scheme)):
    """
    Get repository commits
    """
    if not input.token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{input.owner}/{input.repo}/commits",
                headers={"Authorization": f"Bearer {input.token}"},
                params={"page": input.page, "per_page": input.per_page}
            )
            
            if response.status_code == 200:
                commits = response.json()
                # Fetch additional details for each commit
                detailed_commits = []
                for commit in commits:
                    commit_sha = commit['sha']
                    details_response = await client.get(
                        f"https://api.github.com/repos/{input.owner}/{input.repo}/commits/{commit_sha}",
                        headers={"Authorization": f"Bearer {input.token}"}
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

@router.post("/repos/{owner}/{repo}/setup-webhook")
async def setup_webhook(
    background_tasks: BackgroundTasks,
    input: SetupWebhookInput = Depends(oauth2_scheme)
):
    """
    Automatically set up a webhook for a repository
    """
    if not input.token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    try:
        repo_full_name = f"{input.owner}/{input.repo}"
        logger.info(f"Setting up webhook for {repo_full_name} to {WEBHOOK_URL}")
        
        # First check if a webhook already exists
        async with httpx.AsyncClient() as client:
            hooks_response = await client.get(
                f"https://api.github.com/repos/{input.owner}/{input.repo}/hooks",
                headers={"Authorization": f"Bearer {input.token}"}
            )
            
            if hooks_response.status_code == 200:
                hooks = hooks_response.json()
                
                # Check if a webhook for our app already exists
                for hook in hooks:
                    config = hook.get('config', {})
                    hook_url = config.get('url', '')
                    
                    if WEBHOOK_URL in hook_url:
                        hook_id = str(hook['id'])
                        events = hook.get('events', [])
                        
                        # Update database entry
                        add_or_update_registered_webhook(db_session=get_db(),
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
            else:
                logger.error(f"Error checking existing hooks: {hooks_response.text}")
        
        # Create webhook using GitHub API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/repos/{input.owner}/{input.repo}/hooks",
                headers={"Authorization": f"Bearer {input.token}"},
                json={
                    "name": "web",
                    "active": True,
                    "events": ["push", "pull_request", "issues"],
                    "config": {
                        "url": WEBHOOK_URL,
                        "content_type": "json",
                        "secret": WEBHOOK_SECRET,
                        "insecure_ssl": "0"
                    }
                }
            )
            
            if response.status_code == 201:
                # Successfully created webhook
                hook_data = response.json()
                hook_id = str(hook_data['id'])
                events = hook_data.get('events', [])
                
                # Add to database
                add_or_update_registered_webhook(db_session=get_db(),
                    repository=repo_full_name,
                    hook_id=hook_id,
                    hook_url=WEBHOOK_URL,
                    events=events
                )
                
                logger.info(f"Webhook created successfully: {hook_id}")
                
                # Sync webhooks in background to ensure consistency
                background_tasks.add_task(sync_repository_webhooks, input.owner, input.repo, input.token)
                
                return {"status": "success", "message": "Webhook created successfully", "hook_id": hook_id}
            else:
                # Failed to create webhook
                error_detail = f"Failed to create webhook: {response.text}"
                logger.error(error_detail)
                return {"status": "error", "message": error_detail}
                
    except Exception as e:
        logger.error(f"Error setting up webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def webhook(request: Request):
    """
    GitHub webhook endpoint for receiving repository events
    """
    try:
        event_type = request.headers.get("X-GitHub-Event")
        if not event_type:
            raise HTTPException(status_code=400, detail="X-GitHub-Event header missing")
            
        payload = await request.json()
        repository = payload.get("repository", {})
        repo_name = repository.get("full_name", "unknown")
        
        logger.info(f"Received {event_type} event from {repo_name}")
        
        # Create a webhook event record
        event_id = f"{datetime.now().isoformat()}-{event_type}"
        timestamp = datetime.now().isoformat()
        
        # Save to database
        add_webhook_event(event_id, event_type, repo_name, timestamp, payload,db_session=get_db(),)
        
        # Process push events
        if event_type == "push":
            await process_push_event(payload)
            
        return {"status": "success", "event_id": event_id}
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))