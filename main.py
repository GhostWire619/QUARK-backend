import logging
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
import uvicorn


from app.settings import settings
from app.routes.auth import router as auth_router, verify_token, get_github_user
from app.routes.webhooks import router as webhooks_router
from app.routes.user import router as user_router
from app.routes.logs import router as logs_router
from app.routes.deployments import router as deployments_router
from app.database.database import init_db
from app.utils.middleware import RequestLoggingMiddleware, authenticate_request
from app.websockets.logs import log_manager

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
    title="QUARK - GitHub Webhook & Deployment Manager",
    description="""
    # QUARK: Deployment automation service with GitHub integration
    
    ## Authentication Options
    
    QUARK supports two authentication methods:
    
    1. **Email/Password Authentication**:
       - Register: `POST /auth/register`
       - Login: `POST /auth/login`
       - Returns a JWT token to use for subsequent requests
    
    2. **GitHub OAuth Authentication**:
       - Start OAuth flow: `GET /auth/github/login`
       - System handles callback: `GET /auth/github/callback`
       - Returns a JWT token with GitHub integration
    
    3. **Account Linking**:
       - Link GitHub to existing account: `GET /auth/link-github`
       - This allows accessing GitHub APIs with your regular account
    
    ## How to Authenticate in Swagger UI
    
    1. Click the 🔒 **Authorize** button at the top-right
    2. Enter your JWT token in the "Value" field (without "Bearer" prefix)
    3. Click "Authorize" and close the dialog
    4. All API requests will now include your token
    
    ## Key Features
    
    * 🔐 User authentication (Email/Password and GitHub OAuth)
    * 🔄 Automated webhook management for GitHub repositories
    * 📊 Track and store webhook events
    * 👤 User profile and repository management
    * 🚀 Automated deployments from GitHub repositories
    * 📡 Real-time logs via WebSockets
    
    ## Getting Started
    
    1. Start by registering a new account or logging in with GitHub
    2. Link your GitHub account if using email/password authentication
    3. Set up webhooks for your repositories
    4. Configure deployment settings for your projects
    
    ## GitHub-Dependent Features
    
    Some endpoints require GitHub integration. These will work if:
    - You authenticated using GitHub OAuth, or
    - You linked a GitHub account to your email/password account
    
    ## API Token Management
    
    Your JWT token is valid for 24 hours. To check your current user info:
    - Visit `GET /auth/me` to see your profile and connection status
    
    ## WebSocket Features
    
    The application supports real-time communication via WebSockets:
    - `/ws/logs/{log_id}`: Subscribe to specific log streams
    - `/ws/logs/all`: Subscribe to all logs
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "auth",
            "description": "Authentication operations: register, login, GitHub OAuth, and account management"
        },
        {
            "name": "webhooks",
            "description": "GitHub webhook management and event handling (requires GitHub integration)"
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
            "description": "Deployment configuration and execution (requires GitHub integration)"
        }
    ]
)

# Add security schemes to OpenAPI
app.swagger_ui_parameters = {
    "persistAuthorization": True,
    "defaultModelsExpandDepth": 3,
    "deepLinking": True,
    "displayRequestDuration": True,
    "docExpansion": "list",
    "showExtensions": True,
    "tryItOutEnabled": True,
    "supportedSubmitMethods": ["get", "put", "post", "delete", "options", "head", "patch", "trace"],
    "oauth2RedirectUrl": f"{settings.FRONTEND_URL}/oauth2-redirect.html",
    "filter": True,
    # Add these additional parameters for better token persistence
    "withCredentials": True,
    "persistAuthorization": True
}

# Define HTTP Bearer scheme with better documentation
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
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": """
                JWT token obtained from `/auth/login`, `/auth/register`, or GitHub OAuth. 
                Enter the token value without the 'Bearer' prefix.
                
                Example: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0
            """
        }
    }
    
    # Default security requirement (most routes need authentication)
    security_requirement = [{"HTTPBearer": []}]
    
    # Add global security requirement (this applies to all endpoints by default)
    openapi_schema["security"] = security_requirement
    
    # Process each path and operation to apply correct security requirements
    for path, path_item in openapi_schema["paths"].items():
        # Skip security for auth endpoints that don't need authentication
        if (path.startswith("/auth/login") or 
            path.startswith("/auth/register") or 
            path.startswith("/auth/github/login") or 
            path.startswith("/auth/github/callback") or
            path.startswith("/docs") or 
            path.startswith("/redoc") or
            path.startswith("/openapi.json")):
            
            for method in path_item:
                if method.lower() in ["get", "post", "put", "delete", "patch"]:
                    # Empty array means no security requirements
                    path_item[method]["security"] = []
        
        # For all other endpoints, ensure they have the security requirement
        else:
            for method in path_item:
                if method.lower() in ["get", "post", "put", "delete", "patch"]:
                    # Only add if not already present
                    if "security" not in path_item[method]:
                        path_item[method]["security"] = security_requirement
    
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

# Initialize db
init_db()

# Include routers with tags
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(user_router, prefix="/user", tags=["user"])
app.include_router(webhooks_router, prefix="/api", tags=["webhooks"])
app.include_router(logs_router, prefix="/logs", tags=["logs"])
app.include_router(deployments_router, prefix="/deploy", tags=["deploy"])

# WebSocket endpoints directly on the app (bypassing router auth middleware)
@app.websocket("/ws/logs/{log_id}")
async def websocket_logs(websocket: WebSocket, log_id: str, token: str = None):
    """
    WebSocket endpoint for real-time log updates.
    This endpoint is mounted directly on the app to bypass authentication middleware.
    
    Authentication is handled via a token query parameter.
    """
    try:
        # Verify token if provided
        if token:
            user = verify_token(token)
            if not user:
                await websocket.close(code=4001, reason="Unauthorized")
                return
        
        await log_manager.connect(websocket, log_id)
        
        while True:
            try:
                # Keep the connection alive and wait for client messages
                data = await websocket.receive_text()
                # You can handle client messages here if needed
            except WebSocketDisconnect:
                log_manager.disconnect(websocket, log_id)
                break
            
    except Exception as e:
        try:
            log_manager.disconnect(websocket, log_id)
        except:
            pass
        raise

@app.websocket("/ws/logs/all")
async def websocket_all_logs(websocket: WebSocket, token: str = None):
    """
    WebSocket endpoint for all logs stream.
    This endpoint is mounted directly on the app to bypass authentication middleware.
    
    Authentication is handled via a token query parameter.
    """
    try:
        # Verify token if provided
        if token:
            user = verify_token(token)
            if not user:
                await websocket.close(code=4001, reason="Unauthorized")
                return
        
        await log_manager.connect(websocket, "all_logs")
        
        while True:
            try:
                # Keep the connection alive and wait for client messages
                data = await websocket.receive_text()
                # You can handle client messages here if needed
            except WebSocketDisconnect:
                log_manager.disconnect(websocket, "all_logs")
                break
            
    except Exception as e:
        try:
            log_manager.disconnect(websocket, "all_logs")
        except:
            pass
        raise

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, ssl_certfile=None, ssl_keyfile=None)