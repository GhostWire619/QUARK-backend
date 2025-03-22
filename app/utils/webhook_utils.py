from app.settings import WEBHOOK_URL, WEBHOOK_SECRET, REPOS_FOLDER
from fastapi.responses import JSONResponse
from typing import Dict, Any
import logging
from datetime import datetime
from git import Repo
import httpx
import os
import asyncio

from app.database.webhook_db import (get_db,
    add_or_update_registered_webhook,
    get_registered_webhooks_by_repository, delete_registered_webhook
)

logger = logging.getLogger(__name__)


async def process_push_event(payload: Dict[str, Any]):
    """
    Process a push event
    """
    try:
        repository = payload.get("repository", {})
        repo_name = repository.get("full_name", "")
        repo_url = repository.get("clone_url", "")
        
        if not repo_name or not repo_url:
            logger.warning("Missing repository information in push event")
            return
        
        # Create repository folder path
        repo_path = os.path.join(REPOS_FOLDER, repo_name.replace("/", "_"))
        
        # Check if the repository already exists locally
        if os.path.exists(repo_path):
            # Pull latest changes
            logger.info(f"Pulling latest changes for {repo_name}")
            repo = Repo(repo_path)
            origin = repo.remotes.origin
            origin.pull()
        else:
            # Clone the repository
            logger.info(f"Cloning repository {repo_name}")
            Repo.clone_from(repo_url, repo_path)
            
        logger.info(f"Repository {repo_name} updated successfully")
        
    except Exception as e:
        logger.error(f"Error processing push event: {str(e)}")



async def sync_all_webhooks(token: str):
    """
    Synchronize webhooks for all repositories the user has access to
    """
    try:
        logger.info("Starting full webhook synchronization")
        
        # Get user repositories
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user/repos?per_page=100",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                logger.error(f"Error fetching repositories: {response.text}")
                return
                
            repos = response.json()
        
        # Sync webhooks for each repository
        for repo in repos:
            owner = repo['owner']['login']
            repo_name = repo['name']
            await sync_repository_webhooks(owner, repo_name, token)
            
        logger.info("Full webhook synchronization completed")
    
    except Exception as e:
        logger.error(f"Error in full webhook synchronization: {str(e)}")


async def sync_repository_webhooks(owner: str, repo: str, token: str):
    """
    Synchronize webhooks for a specific repository
    """
    try:
        logger.info(f"Syncing webhooks for {owner}/{repo}")
        repo_full_name = f"{owner}/{repo}"
        
        # Get webhooks from GitHub
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/hooks",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                logger.error(f"Error fetching hooks for {repo_full_name}: {response.text}")
                return False
                
            github_hooks = response.json()
            
        # Get registered webhooks from database
        db_hooks = get_registered_webhooks_by_repository(repo_full_name,db_session=get_db())
        db_hook_ids = {hook['hook_id'] for hook in db_hooks}
        
        # Add or update webhooks in database
        for hook in github_hooks:
            hook_id = str(hook['id'])
            config = hook.get('config', {})
            hook_url = config.get('url', '')
            events = hook.get('events', [])
            
            # Only track webhooks that point to our app
            if WEBHOOK_URL in hook_url:
                add_or_update_registered_webhook(db_session=get_db(),
                    repository=repo_full_name,
                    hook_id=hook_id,
                    hook_url=hook_url,
                    events=events
                )
                
                if hook_id in db_hook_ids:
                    db_hook_ids.remove(hook_id)
        
        # Remove webhooks from database that no longer exist in GitHub
        for hook_id in db_hook_ids:
            delete_registered_webhook(repo_full_name, hook_id,db_session=get_db())
            
        logger.info(f"Webhook sync completed for {repo_full_name}")
        return True
    
    except Exception as e:
        logger.error(f"Error syncing webhooks for {owner}/{repo}: {str(e)}")
        return False
