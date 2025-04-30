from fastapi import APIRouter, HTTPException, Depends, status
import logging
import httpx
from typing import Dict, List, Any

from app.schemas.user_models import UserCreate
from app.database.user_crud import create_user
from app.database.database import get_db
from sqlalchemy.orm import Session
from app.settings import settings
from app.routes.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

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
    current_user: Dict = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """
    Retrieves the authenticated user's GitHub profile and creates/updates local user record.
    
    This endpoint:
    1. Fetches user profile from GitHub using the stored GitHub token
    2. Creates or updates local user record
    3. Returns complete GitHub profile information
    
    The local user record is created with:
    - GitHub username
    - GitHub email (if public)
    - System-generated password
    
    Args:
        current_user (Dict): Authenticated user information including 'github_token'
        db_session (Session): Database session
    
    Returns:
        Dict[str, Any]: Complete GitHub user profile
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
        
    # Check if GitHub is connected and token is available
    if not current_user.get("github_connected") or not current_user.get("github_token"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not linked or token unavailable. Please link your GitHub account."
        )

    github_api_token = current_user.get("github_token")
    
    try:
        # Create or update local user record (this part might need review - does it always need to run?)
        # username = current_user.get("username")
        # email = current_user.get("email")
        # user_data = UserCreate(username=username, email=email, password=settings.PASSWORD)
        # new_user = create_user(db_session, user_data)
        # if new_user is None:
        #     logger.info(f"User {username} already exists")
        # else:
        #     logger.info(f"New user {new_user.username} has been created")
        
        # Get full GitHub profile using the stored GitHub token
        async with httpx.AsyncClient() as client:
            logger.debug(f"Making GitHub API request to /user with token: {github_api_token[:4]}...")
            response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {github_api_token}"}
            )
            
            if response.status_code == 200:
                github_user = response.json()
                # Ensure the email is included if missing from GitHub profile but present in our record
                if ("email" not in github_user or not github_user["email"]) and current_user.get("email"):
                    github_user["email"] = current_user.get("email")
                logger.info(f"Successfully fetched GitHub profile for {github_user.get('login')}")
                return github_user
            else:
                # If we can't get the full profile, raise an error
                error_detail = f"Failed to fetch GitHub profile: {response.status_code} - {response.text}"
                logger.warning(error_detail)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, # 502 suggests an issue talking to the upstream service (GitHub)
                    detail=error_detail
                )
    
    except httpx.RequestError as exc:
        error_detail = f"Error communicating with GitHub API: {exc}"
        logger.error(error_detail)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=error_detail)
    except Exception as e:
        # Catch-all for other unexpected errors
        error_detail = f"Error processing user profile: {str(e)}"
        logger.error(error_detail, exc_info=True) # Log traceback for unexpected errors
        raise HTTPException(status_code=500, detail=error_detail)
    
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
        400: {"description": "GitHub account not linked or token unavailable"},
        500: {"description": "Server error"}
    }
)
async def get_user_repos(current_user: Dict = Depends(get_current_user)):
    """
    Retrieves the authenticated user's GitHub repositories using their stored token.
    
    This endpoint:
    1. Checks if the user has a linked GitHub account and token.
    2. Fetches up to 100 most recently updated repositories from GitHub.
    3. Includes both public and private repositories.
    4. Returns detailed repository information.
    
    The repositories are sorted by last update time and include:
    - Repository metadata
    - Visibility settings
    - Last update time
    - Description
    
    Args:
        current_user (Dict): Authenticated user information including 'github_token'
    
    Returns:
        List[Dict[str, Any]]: List of repository information
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
        
    # Check if GitHub is connected and token is available
    if not current_user.get("github_connected") or not current_user.get("github_token"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not linked or token unavailable. Please link your GitHub account."
        )
        
    github_api_token = current_user.get("github_token")
    
    try:
        auth_header = f"Bearer {github_api_token}"
        logger.info(f"Getting repositories for user: {current_user.get('username')} using stored token.")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user/repos?sort=updated&per_page=100",
                headers={"Authorization": auth_header}
            )
            
            if response.status_code == 200:
                logger.info(f"Successfully fetched repositories for {current_user.get('username')}")
                return response.json()
            else:
                error_message = f"GitHub API error fetching repos: {response.status_code}"
                logger.error(f"{error_message} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, 
                    detail=f"{error_message}. Please check your GitHub token permissions or validity."
                )
    
    except httpx.RequestError as exc:
        error_detail = f"Error communicating with GitHub API for repos: {exc}"
        logger.error(error_detail)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=error_detail)
    except Exception as e:
        error_detail = f"Error fetching repositories: {str(e)}"
        logger.error(error_detail, exc_info=True)
        raise HTTPException(status_code=500, detail=error_detail)