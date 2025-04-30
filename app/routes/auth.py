from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Depends, Header, Response, Cookie
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, OAuth2PasswordBearer, HTTPAuthorizationCredentials
import httpx
import logging
from typing import Dict, Optional, Any
import jwt
import os
from datetime import datetime, timedelta

from app.settings import settings
from app.database.database import get_db
from app.database.user_crud import (
    get_user_by_email, create_user, get_user_by_id, 
    verify_password, create_or_update_github_user,
    link_github_account, get_user_by_github_id
)
from app.schemas.user_models import (
    UserResponse, LoginRequest, 
    RegisterRequest, TokenResponse, GitHubTokenResponse
)
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger(__name__)
http_bearer_scheme = HTTPBearer(auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="auth/login",
    auto_error=False,
    description="JWT token obtained from the login or register endpoints"
)

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", settings.PASSWORD or "your-secret-key")
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
    logger.debug(f"Attempting to verify token: {token[:10]}...") # Log first few chars
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        logger.debug(f"Token verified successfully for sub: {payload.get('sub')}")
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning(f"Token has expired: {token[:10]}...")
        return None
    except jwt.PyJWTError as e:
        logger.warning(f"Token verification failed: {str(e)} - Token: {token[:10]}...")
        return None

async def get_user_from_token(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer_scheme),
    db: Session = Depends(get_db)
) -> Optional[Dict[str, Any]]:
    """Get user from JWT token provided via HTTP Bearer authentication.
    Handles token verification and user lookup.
    Used as a dependency for protected routes.
    """
    if auth is None:
        logger.warning("get_user_from_token: No valid HTTPBearer credentials found.")
        return None
        
    token = auth.credentials
    logger.debug(f"get_user_from_token received token via HTTPBearer: {token[:10]}...")
    
    payload = verify_token(token)
    if not payload or "sub" not in payload:
        logger.warning(f"Token verification failed or 'sub' missing for token: {token[:10]}...")
        return None
    
    user_id = payload["sub"]
    user = get_user_by_id(db, user_id)
    if not user:
        logger.warning(f"User not found in DB for sub: {user_id}")
        return None
    
    logger.info(f"Authenticated user: {user.username} (ID: {user.id})")
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "github_connected": bool(user.github_id),
        "github_token": user.github_access_token,
        "auth_type": payload.get("auth_type", "github" if user.github_id else "password"),
        "original_token": token
    }

@router.post(
    "/register",
    summary="Register a new user",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "User created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "user": {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "username": "johndoe",
                            "email": "john@example.com",
                            "github_connected": False,
                            "auth_type": "password"
                        }
                    }
                }
            }
        },
        400: {"description": "Email already registered"},
    }
)
async def register(user_data: RegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new user with email and password.
    
    This endpoint:
    1. Creates a new user in the system
    2. Returns a JWT token for immediate authentication
    3. The token should be used in the Authorization header for subsequent requests
    
    After registration, you can:
    - Link your GitHub account via `/auth/link-github`
    - Access non-GitHub endpoints immediately
    - Check your profile via `/auth/me`
    """
    # Check if email already exists
    existing_user = get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    new_user = create_user(db, user_data)
    
    # Generate JWT token
    token_data = {
        "sub": new_user.id,
        "username": new_user.username,
        "email": new_user.email,
        "auth_type": "password"
    }
    access_token = create_jwt_token(token_data)
    
    # Return token and user data
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "github_connected": False,
            "auth_type": "password"
        }
    }

@router.post(
    "/login",
    summary="Login with email and password",
    response_model=TokenResponse,
    responses={
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "user": {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "username": "johndoe",
                            "email": "john@example.com",
                            "github_connected": True,
                            "auth_type": "password"
                        }
                    }
                }
            }
        },
        401: {"description": "Invalid credentials"},
    }
)
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Login with email and password.
    
    This endpoint:
    1. Authenticates a user with email/password
    2. Returns a JWT token for authentication
    3. The token should be used in the Authorization header for subsequent requests
    
    If you've previously linked a GitHub account:
    - The response will include `github_connected: true`
    - You'll be able to access GitHub-dependent endpoints automatically
    - Your JWT token will work for all API endpoints
    """
    user = get_user_by_email(db, login_data.email)
    if not user or not verify_password(user, login_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate JWT token
    token_data = {
        "sub": user.id,
        "username": user.username,
        "email": user.email,
        "auth_type": "password"
    }
    access_token = create_jwt_token(token_data)
    
    # Return token and user data
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "github_connected": bool(user.github_id),
            "github_token": user.github_access_token,
            "auth_type": "password"
        }
    }

@router.get(
    "/github/login",
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
async def github_login(user_id: Optional[str] = None):
    """
    Start the GitHub OAuth login process.
    
    This endpoint:
    1. Generates a GitHub authorization URL
    2. The client should redirect the user to this URL
    3. GitHub will then redirect back to your callback URL
    
    Required permissions:
    - `repo`: Full control of private repositories
    - `admin:repo_hook`: Full control of repository hooks
    
    This endpoint can be used in two ways:
    1. New users signing in with GitHub (without user_id parameter)
    2. Existing users linking a GitHub account (with user_id parameter)
    
    For account linking, pass the user's ID in the user_id query parameter.
    """
    if not settings.CLIENT_ID:
        raise HTTPException(status_code=500, detail="CLIENT_ID not configured")
    
    scope = "repo admin:repo_hook"
    state = user_id or ""  # Pass user_id as state for account linking
    github_auth_url = f"https://github.com/login/oauth/authorize?client_id={settings.CLIENT_ID}&redirect_uri={settings.REDIRECT_URI}&scope={scope}&state={state}"
    
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
async def github_callback(code: str, state: Optional[str] = None, background_tasks: BackgroundTasks = None, db: Session = Depends(get_db)):
    """
    Handles the GitHub OAuth callback process.
    
    This endpoint:
    1. Receives the temporary code from GitHub
    2. Exchanges it for an access token
    3. Retrieves user information from GitHub
    4. Creates or updates user in our database
    5. Redirects to the frontend with our JWT token
    
    Args:
        code (str): Temporary code from GitHub OAuth process
        state (str, optional): State parameter, used for account linking
        background_tasks (BackgroundTasks): FastAPI background tasks handler
        db (Session): Database session
    
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
            # Get GitHub access token
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
            
            github_token = token_data.get("access_token")
            
            if not github_token:
                logger.error("No access token in GitHub response")
                return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=no_token")
            
            # Use token to get user information
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "X-GitHub-Api-Version": "2022-11-28"
                }
            )
            
            if user_response.status_code != 200:
                logger.error(f"GitHub API error: {user_response.text}")
                return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=github_api_error")
            
            github_user_data = user_response.json()
            github_user_data["token"] = github_token  # Add token to user data
            
            # Check if we're linking to an existing account
            if state and state.strip():
                user_id = state.strip()
                user = get_user_by_id(db, user_id)
                
                # If user exists, link GitHub account
                if user:
                    linked_user = link_github_account(db, user.id, github_user_data)
                    
                    # Create JWT token for our system
                    token_data = {
                        "sub": linked_user.id,
                        "username": linked_user.username,
                        "email": linked_user.email,
                        "auth_type": "password",  # Still a password account, but linked
                        "github_id": str(github_user_data.get("id"))
                    }
                    our_token = create_jwt_token(token_data)
                    
                    # Redirect to frontend with token
                    return RedirectResponse(
                        url=f"{settings.FRONTEND_URL}/login?token={our_token}&provider=github&linked=true"
                    )
            
            # Create or update user in our database
            user = create_or_update_github_user(db, github_user_data)
            
            # Create JWT token for our system
            token_data = {
                "sub": user.id,
                "username": user.username,
                "email": user.email,
                "auth_type": "github",
                "github_id": str(github_user_data.get("id"))
            }
            our_token = create_jwt_token(token_data)
            
            # Redirect to frontend with token
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/login?token={our_token}&provider=github"
            )
    
    except Exception as e:
        logger.error(f"Error in GitHub OAuth callback: {str(e)}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=server_error")

@router.get(
    "/me",
    summary="Get current user information",
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Successfully retrieved user information",
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "email": "john@example.com",
                        "github_connected": True,
                        "github_token": "gho_abc123...",
                        "auth_type": "password"
                    }
                }
            }
        },
        401: {"description": "Not authenticated"},
    }
)
async def get_me(current_user: Dict[str, Any] = Depends(get_user_from_token)):
    """
    Get information about the currently authenticated user.
    
    This endpoint:
    1. Returns details about the authenticated user
    2. Shows GitHub connection status
    3. Indicates authentication type
    
    Authentication required:
    - Must include a valid JWT token in the Authorization header
    - Works with both regular and GitHub-authenticated accounts
    
    The response includes:
    - User profile information
    - GitHub connection status
    - Authentication type (password or github)
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    return current_user

async def get_current_user(token: Optional[str] = Depends(http_bearer_scheme), db: Session = Depends(get_db)):
    """
    Get the authenticated user from the JWT token.
    
    This function:
    1. Validates the JWT token provided via HTTP Bearer
    2. Returns the user information if authenticated
    3. Returns None if not authenticated
    
    Args:
        token: HTTPAuthorizationCredentials from request (or None)
        db: Database session
        
    Returns:
        Optional[Dict[str, Any]]: User information if authenticated, None otherwise
    """
    if token is None:
        logger.warning("get_current_user: No HTTPBearer credentials provided.")
        return None
    
    actual_token = token.credentials
    payload = verify_token(actual_token)
    if not payload or "sub" not in payload:
        logger.warning(f"get_current_user: Token verification failed or 'sub' missing.")
        return None
    
    user_id = payload["sub"]
    user = get_user_by_id(db, user_id)
    if not user:
        logger.warning(f"get_current_user: User not found for sub: {user_id}")
        return None
    
    logger.info(f"get_current_user succeeded for user: {user.username}")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "github_connected": bool(user.github_id),
        "github_token": user.github_access_token,
        "auth_type": payload.get("auth_type", "github" if user.github_id else "password")
    }

async def get_github_user(token: str):
    """
    Get the authenticated user from the GitHub token.
    
    This function:
    1. Validates the GitHub token by requesting user data
    2. Returns the user information if authenticated
    3. Returns None if not authenticated
    
    Args:
        token: GitHub token
        
    Returns:
        Optional[Dict[str, Any]]: User information if authenticated, None otherwise
    """
    if not token:
        logger.warning("No token provided")
        return None
    
    try:
        # Log masked token for debugging (showing only first and last 4 chars)
        token_length = len(token) if isinstance(token, str) else 0
        if token_length > 8:
            masked_token = token[:4] + '*' * (token_length - 8) + token[-4:]
            logger.info(f"Using token: {masked_token}")
        else:
            logger.warning("Token too short or invalid format")
            return None
            
        async with httpx.AsyncClient() as client:
            logger.info("Making GitHub API request to validate token")
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
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
                "token": token  # Include the token for downstream use
            }
    
    except Exception as e:
        logger.error(f"Error authenticating user: {str(e)}")
        return None

@router.get(
    "/link-github",
    summary="Link GitHub account to current user",
    response_model=Dict[str, str],
    responses={
        200: {
            "description": "Successfully generated GitHub OAuth URL for linking",
            "content": {
                "application/json": {
                    "example": {"login_url": "https://github.com/login/oauth/authorize?client_id=xxx&redirect_uri=xxx&scope=repo admin:repo_hook&state=user_id"}
                }
            }
        },
        401: {"description": "Not authenticated"},
    }
)
async def link_github(current_user: Dict[str, Any] = Depends(get_user_from_token)):
    """
    Generate a GitHub OAuth URL for linking a GitHub account to the current user.
    
    This endpoint:
    1. Creates a GitHub authorization URL with your user ID in the state parameter
    2. The client should redirect the user to this URL
    3. After GitHub authentication, your accounts will be linked
    
    Authentication required:
    - Must include a valid JWT token in the Authorization header
    
    After linking:
    - You can access GitHub-dependent endpoints
    - Your JWT token will automatically include GitHub permissions
    - All API calls will work with a single authentication method
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    # Use the github_login endpoint with the current user ID as state
    return await github_login(user_id=current_user["id"])