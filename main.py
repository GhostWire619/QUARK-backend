import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
import uvicorn


from app.settings import FRONTEND_URL
from app.routes.auth import router as auth_router
from app.routes.webhooks import router as webhooks_router
from app.routes.user import router as user_router
from  app.database.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Create FastAPI app
app = FastAPI(
    title="GitHub Webhook Manager",
    description="""
    A comprehensive GitHub webhook management system that allows you to:
    
    ## Key Features
    * 🔐 Authenticate with GitHub using OAuth
    * 🔄 Automatically set up and manage webhooks for repositories
    * 📊 Track and store webhook events
    * 👤 Manage user profiles and repository access
    
    ## Authentication
    The API uses GitHub OAuth for authentication. All authenticated endpoints require a valid GitHub access token.
    
    ## Webhook Management
    - Automatically create and configure webhooks for repositories
    - Store and track webhook events
    - View commit history and repository information
    
    ## User Management
    - View and manage user profiles
    - Access repository listings
    - Track user-specific webhook configurations
    
    ## Getting Started
    1. Start by authenticating through the `/auth/login` endpoint
    2. Use the received token for all authenticated requests
    3. Set up webhooks for your repositories using `/api/repos/{owner}/{repo}/setup-webhook`
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "auth",
            "description": "Authentication operations with GitHub OAuth"
        },
        {
            "name": "webhooks",
            "description": "Webhook management and event handling"
        },
        {
            "name": "user",
            "description": "User profile and repository management"
        }
    ]
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#initialize db
init_db()

# Include routers with tags
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(user_router, prefix="/user", tags=["user"])
app.include_router(webhooks_router, prefix="/api", tags=["webhooks"])


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)