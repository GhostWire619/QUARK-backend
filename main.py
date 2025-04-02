import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
import uvicorn


from app.settings import settings
from app.routes.auth import router as auth_router
from app.routes.webhooks import router as webhooks_router
from app.routes.user import router as user_router
from app.routes.logs import router as logs_router
from app.routes.deployments import router as deployments_router
from app.database.database import init_db
from app.utils.middleware import RequestLoggingMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Security scheme
security_bearer = HTTPBearer(auto_error=False)

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
    * 🚀 Automated deployments from GitHub repositories
    
    ## Authentication
    The API uses GitHub OAuth for authentication. All authenticated endpoints require a valid GitHub access token.
    
    To authenticate in Swagger UI:
    1. Click the "Authorize" button at the top-right
    2. Enter your GitHub token in the Value field (without "Bearer" prefix)
    3. Click "Authorize" and close the dialog
    
    ## Webhook Management
    - Automatically create and configure webhooks for repositories
    - Store and track webhook events
    - View commit history and repository information
    
    ## User Management
    - View and manage user profiles
    - Access repository listings
    - Track user-specific webhook configurations
    
    ## Deployment Platform
    - Configure automated deployments for repositories
    - Define build, deploy, and post-deploy commands
    - View deployment history and logs
    - Support for multiple environments (dev, test, staging, prod)
    
    ## Getting Started
    1. Start by authenticating through the `/auth/login` endpoint
    2. Use the received token for all authenticated requests
    3. Set up webhooks for your repositories using `/api/repos/{owner}/{repo}/setup-webhook`
    4. Configure deployments using `/deploy/configs`
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
        },
        {
            "name": "logs",
            "description": "API request logging and monitoring"
        },
        {
            "name": "deploy",
            "description": "Deployment configuration and execution"
        }
    ]
)

# Add security schemes to OpenAPI
app.swagger_ui_parameters = {
    "persistAuthorization": True,
}

# Define HTTP Bearer scheme
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    # Get the default OpenAPI schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    
    # Define security scheme
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer"
        }
    }
    
    # Apply security globally
    openapi_schema["security"] = [{"HTTPBearer": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
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
app.include_router(logs_router, prefix="/logs", tags=["logs"])
app.include_router(deployments_router, prefix="/deploy", tags=["deploy"])


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, ssl_certfile=None, ssl_keyfile=None)