from fastapi import APIRouter, HTTPException, Depends, status
import logging
import httpx

from app.schemas.user_models import (UserCreate)
from app.database.user_crud import create_user
from app.database.database import get_db
from sqlalchemy.orm import Session
from app.settings import PASSWORD
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)



@router.get("/profile")
async def get_user_profile(token: str = Depends(oauth2_scheme),db_session:Session=Depends(get_db)):
    """
    Get GitHub user profile
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
                response = response.json()
                github_user = response.json()
                # Extract required fields from GitHub response
                username = github_user.get("login")
                email = github_user.get("email")
                user_data = UserCreate(username=username, email=email, password=PASSWORD)
                new_user = create_user(db_session, user_data)
                logger.info(f" a new user {new_user} has been created")
                return response.json()
            else:
                logger.error(f"GitHub API error: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
    
    except Exception as e:
        logger.error(f"Error fetching user profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/repos")
async def get_user_repos(token: str = Depends(oauth2_scheme)):
    """
    Get GitHub user repositories
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