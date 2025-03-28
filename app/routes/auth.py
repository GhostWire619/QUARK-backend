from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from fastapi.responses import RedirectResponse
import httpx
import logging
from typing import Dict

from app.settings import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, FRONTEND_URL

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/login",
    summary="Initialize GitHub OAuth Login",
    response_model=Dict[str, str],
    responses={
        200: {
            "description": "Successfully generated GitHub OAuth URL",
            "content": {
                "application/json": {
                    "example": {"login_url": "https://github.com/login/oauth/authorize?client_id=xxx&redirect_uri=xxx&scope=repo admin:repo_hook"}
                }
            }
        },
        500: {
            "description": "Server configuration error",
            "content": {
                "application/json": {
                    "example": {"detail": "CLIENT_ID not configured"}
                }
            }
        }
    }
)
async def login():
    """
    Initiates the GitHub OAuth login process.
    
    This endpoint generates a GitHub OAuth URL with the following permissions:
    - `repo`: Full control of private repositories
    - `admin:repo_hook`: Full control of repository hooks
    
    Returns:
        dict: Contains the GitHub OAuth URL for the frontend to redirect to
    """
    if not CLIENT_ID:
        raise HTTPException(status_code=500, detail="CLIENT_ID not configured")
    scope = "repo admin:repo_hook"
    github_auth_url = f"https://github.com/login/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope={scope}"
    return {"login_url": github_auth_url}

@router.get(
    "/callback",
    summary="GitHub OAuth Callback",
    responses={
        302: {
            "description": "Redirect to frontend with access token or error",
        },
        500: {
            "description": "Server error during OAuth process",
            "content": {
                "application/json": {
                    "example": {"detail": "Error in GitHub OAuth callback"}
                }
            }
        }
    }
)
async def callback(code: str, background_tasks: BackgroundTasks):
    """
    Handles the GitHub OAuth callback process.
    
    This endpoint:
    1. Receives the temporary code from GitHub
    2. Exchanges it for an access token
    3. Redirects to the frontend with the token or error
    
    Args:
        code (str): Temporary code from GitHub OAuth process
        background_tasks (BackgroundTasks): FastAPI background tasks handler
    
    Returns:
        RedirectResponse: Redirects to frontend with token or error message
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CLIENT_ID or CLIENT_SECRET not configured"
        )
    
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