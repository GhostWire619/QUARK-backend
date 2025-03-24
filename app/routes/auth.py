from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse
import httpx
import logging

from app.settings import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, FRONTEND_URL

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/login")
async def login():
    if not CLIENT_ID:
        raise HTTPException(status_code=500, detail="CLIENT_ID not configured")
    scope = "repo admin:repo_hook"
    github_auth_url = f"https://github.com/login/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope={scope}"
    return {"login_url": github_auth_url}

@router.get("/callback")
async def callback(code: str, background_tasks: BackgroundTasks):
    """
    GitHub OAuth callback
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="CLIENT_ID or CLIENT_SECRET not configured")
    
    try:
        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": REDIRECT_URI
                },
                headers={"Accept": "application/json"}
            )
            
            token_data = response.json()
            
            if "error" in token_data:
                logger.error(f"GitHub OAuth error: {token_data['error']}")
                return RedirectResponse(url=f"{FRONTEND_URL}/login?error={token_data['error']}")
            
            access_token = token_data.get("access_token")
            
            if not access_token:
                logger.error("No access token in GitHub response")
                return RedirectResponse(url=f"{FRONTEND_URL}/login?error=no_token")
            
            # Redirect to frontend with token
            return RedirectResponse(url=f"{FRONTEND_URL}/login?token={access_token}")
    
    except Exception as e:
        logger.error(f"Error in GitHub OAuth callback: {str(e)}")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=server_error")