from fastapi import APIRouter, HTTPException, Depends, status
import logging
import httpx
from typing import Dict, List, Any

from app.schemas.user_models import UserCreate
from app.database.user_crud import create_user
from app.database.database import get_db
from sqlalchemy.orm import Session
from app.settings import PASSWORD
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

@router.get(
    "/profile",
    summary="Get User Profile",
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Successfully retrieved user profile",
            "content": {
                "application/json": {
                    "example": {
                        "login": "username",
                        "id": 12345,
                        "name": "Full Name",
                        "email": "user@example.com",
                        "public_repos": 10,
                        "followers": 20,
                        "following": 30
                    }
                }
            }
        },
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"}
    }
)
async def get_user_profile(
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db)
):
    """
    Retrieves the authenticated user's GitHub profile and creates/updates local user record.
    
    This endpoint:
    1. Fetches user profile from GitHub
    2. Creates or updates local user record
    3. Returns complete GitHub profile information
    
    The local user record is created with:
    - GitHub username
    - GitHub email (if public)
    - System-generated password
    
    Args:
        token (str): GitHub access token
        db_session (Session): Database session
    
    Returns:
        Dict[str, Any]: Complete GitHub user profile
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                github_user = response.json()
                username = github_user.get("login")
                email = github_user.get("email")
                user_data = UserCreate(username=username, email=email, password=PASSWORD)
                new_user = create_user(db_session, user_data)
                if new_user is None:
                    logger.info(f"User {username} already exists")
                else:
                    logger.info(f"New user {new_user.username} has been created")
                return github_user
            else:
                logger.error(f"GitHub API error: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
    
    except Exception as e:
        logger.error(f"Error fetching user profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get(
    "/repos",
    summary="Get User Repositories",
    response_model=List[Dict[str, Any]],
    responses={
        200: {
            "description": "Successfully retrieved user repositories",
            "content": {
                "application/json": {
                    "example": [{
                        "id": 12345,
                        "name": "repo-name",
                        "full_name": "username/repo-name",
                        "private": False,
                        "description": "Repository description",
                        "updated_at": "2024-03-28T12:00:00Z"
                    }]
                }
            }
        },
        401: {"description": "Not authenticated"},
        500: {"description": "Server error"}
    }
)
async def get_user_repos(token: str = Depends(oauth2_scheme)):
    """
    Retrieves the authenticated user's GitHub repositories.
    
    This endpoint:
    1. Fetches up to 100 most recently updated repositories
    2. Includes both public and private repositories
    3. Returns detailed repository information
    
    The repositories are sorted by last update time and include:
    - Repository metadata
    - Visibility settings
    - Last update time
    - Description
    
    Args:
        token (str): GitHub access token
    
    Returns:
        List[Dict[str, Any]]: List of repository information
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user/repos?sort=updated&per_page=100",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"GitHub API error: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
    
    except Exception as e:
        logger.error(f"Error fetching user repositories: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))