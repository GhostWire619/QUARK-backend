from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Depends, Header, Response, Cookie
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, OAuth2PasswordBearer
import httpx
import logging
from typing import Dict, Optional, Any
import jwt
import os
from datetime import datetime, timedelta

from app.settings import settings
from app.database.database import get_db
from app.database.user_crud import get_user_by_email, create_user, get_user_by_id

router = APIRouter()
logger = logging.getLogger(__name__)
http_bearer = HTTPBearer(auto_error=False)

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")  # Change in production
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 60 * 24  # 24 hours

def create_jwt_token(data: Dict[str, Any]) -> str:
    """Create a new JWT token"""
    expiration = datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    to_encode = data.copy()
    to_encode.update({"exp": expiration})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify a JWT token and return the decoded payload"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        return None
    except jwt.JWTError as e:
        logger.warning(f"Token verification failed: {str(e)}")
        return None

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
    if not settings.CLIENT_ID:
        raise HTTPException(status_code=500, detail="CLIENT_ID not configured")
    scope = "repo admin:repo_hook"
    github_auth_url = f"https://github.com/login/oauth/authorize?client_id={settings.CLIENT_ID}&redirect_uri={settings.REDIRECT_URI}&scope={scope}"
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
    if not settings.CLIENT_ID or not settings.CLIENT_SECRET:
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
                    "client_id": settings.CLIENT_ID,
                    "client_secret": settings.CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.REDIRECT_URI
                },
                headers={"Accept": "application/json"}
            )
            
            token_data = response.json()
            
            if "error" in token_data:
                logger.error(f"GitHub OAuth error: {token_data['error']}")
                return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={token_data['error']}")
            
            access_token = token_data.get("access_token")
            
            if not access_token:
                logger.error("No access token in GitHub response")
                return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=no_token")
            
            # Redirect to frontend with token
            return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?token={access_token}")
    
    except Exception as e:
        logger.error(f"Error in GitHub OAuth callback: {str(e)}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=server_error")

async def get_current_user(token: Optional[HTTPBearer] = Depends(http_bearer)) -> Optional[Dict[str, Any]]:
    """
    Get the authenticated user from the GitHub token.
    
    This function:
    1. Validates the GitHub token by requesting user data
    2. Returns the user information if authenticated
    3. Returns None if not authenticated
    
    Args:
        token: HTTPAuthorizationCredentials from bearer token
        
    Returns:
        Optional[Dict[str, Any]]: User information if authenticated, None otherwise
    """
    if not token:
        logger.warning("No token provided")
        return None
    
    actual_token = token.credentials if hasattr(token, 'credentials') else token
    logger.info(f"Token type: {type(actual_token)}")
    
    try:
        # Log masked token for debugging (showing only first and last 4 chars)
        token_length = len(actual_token) if isinstance(actual_token, str) else 0
        if token_length > 8:
            masked_token = actual_token[:4] + '*' * (token_length - 8) + actual_token[-4:]
            logger.info(f"Using token: {masked_token}")
        else:
            logger.warning("Token too short or invalid format")
            return None
            
        async with httpx.AsyncClient() as client:
            logger.info("Making GitHub API request to validate token")
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {actual_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "X-GitHub-Api-Version": "2022-11-28"
                }
            )
            
            status_code = response.status_code
            logger.info(f"GitHub API response status: {status_code}")
            
            if status_code == 401:
                logger.error("Token is invalid or expired")
                return None
            elif status_code == 403:
                logger.error("Token lacks required permissions")
                return None
            elif status_code != 200:
                logger.error(f"GitHub API error: {response.text}")
                return None
            
            user_data = response.json()
            logger.info(f"Successfully authenticated as GitHub user: {user_data.get('login')}")
            
            # Verify required scopes
            scopes = response.headers.get("X-OAuth-Scopes", "").split(", ")
            required_scopes = ["repo", "admin:repo_hook"]
            missing_scopes = [scope for scope in required_scopes if scope not in scopes]
            
            if missing_scopes:
                logger.error(f"Token missing required scopes: {', '.join(missing_scopes)}")
                return None
            
            return {
                "id": str(user_data.get("id")),
                "username": user_data.get("login"),
                "email": user_data.get("email") or f"{user_data.get('login')}@github.com",
                "name": user_data.get("name"),
                "avatar_url": user_data.get("avatar_url"),
                "token": actual_token  # Include the token for downstream use
            }
    
    except Exception as e:
        logger.error(f"Error authenticating user: {str(e)}")
        return None