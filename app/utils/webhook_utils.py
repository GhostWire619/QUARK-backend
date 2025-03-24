from app.settings import WEBHOOK_URL, WEBHOOK_SECRET
import logging

logger = logging.getLogger(__name__)

async def create_webhook(client, owner, repo, token):
    """Create a new webhook for the repository"""
    response = await client.post(
        f"https://api.github.com/repos/{owner}/{repo}/hooks",
        headers={"Authorization": f"Bearer {token}","ngrok-skip-browser-warning": "1"},
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
        return response.json()
    else:
        error_detail = f"Failed to create webhook: {response.text}"
        logger.error(error_detail)
        return None


async def check_existing_webhook(client, owner, repo, token):
    """Check if a webhook already exists for the repository"""
    hooks_response = await client.get(
        f"https://api.github.com/repos/{owner}/{repo}/hooks",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if hooks_response.status_code != 200:
        logger.error(f"Error checking existing hooks: {hooks_response.text}")
        return None
    
    hooks = hooks_response.json()
    
    # Check if a webhook for our app already exists
    for hook in hooks:
        config = hook.get('config', {})
        hook_url = config.get('url', '')
        
        if WEBHOOK_URL in hook_url:
            return hook
    
    return None
