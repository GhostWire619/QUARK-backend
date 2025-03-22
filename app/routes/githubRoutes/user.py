from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks, status
from fastapi.responses import JSONResponse
from typing import Dict, Any, List
import logging
from datetime import datetime
import httpx


from fastapi.security import OAuth2PasswordBearer
router = APIRouter()
logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)



@router.get("/profile")
async def get_user_profile(token: str = Depends(oauth2_scheme)):
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