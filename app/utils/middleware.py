import time
import json
import logging
from typing import Optional, Dict, Any, Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import iterate_in_threadpool
from sqlalchemy.orm import Session
from app.database.database import RequestLogDB, SessionLocal
from app.routes.auth import verify_token
from app.database.user_crud import get_user_by_id

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip WebSocket requests
        if request.url.path.startswith("/ws"):
            return await call_next(request)

        # Record start time
        start_time = time.time()
        
        # Get client details
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        # Get method and path
        method = request.method
        path = request.url.path
        
        # Initialize variables for tracking
        status_code = 500  # Default to error status
        user_id = None
        username = None
        request_data = None

        # Attempt to get user from session if available
        if hasattr(request.state, "user"):
            user_id = getattr(request.state.user, "id", None)
            username = getattr(request.state.user, "username", None)

        # Process request with auth enhancement
        try:
            # Enhance request with authentication
            request = await self._enhance_request_auth(request)
            
            # Process the request
            response = await call_next(request)
            
            status_code = response.status_code
            
            # Try to extract real user info from the response
            if user_id == "authenticated-user" and hasattr(response, "user_id"):
                user_id = response.user_id
                username = getattr(response, "username", None)
            
            # Calculate request processing time
            process_time = int((time.time() - start_time) * 1000)
            
            # Get response body
            response_body = None
            if hasattr(response, "body"):
                try:
                    response_body = json.loads(response.body.decode())
                except:
                    response_body = None

            # Create log entry
            try:
                db = SessionLocal()
                log_entry = RequestLogDB(
                    method=method,
                    path=path,
                    status_code=status_code,
                    response_time=process_time,
                    request_body=json.dumps(request_data) if request_data else None,
                    response_body=json.dumps(response_body) if response_body else None,
                    headers=json.dumps(dict(request.headers)),
                    client_ip=client_ip,
                    user_agent=user_agent
                )
                db.add(log_entry)
                db.commit()
                db.refresh(log_entry)
                
                # Broadcast the log entry
                log_entry.broadcast_log()
                
            except Exception as e:
                logger.error(f"Error logging request: {str(e)}")
            finally:
                db.close()
            
            # Add processing time header
            response.headers["X-Process-Time"] = str(process_time)
            return response
            
        except Exception as e:
            # Log unhandled exceptions
            logger.error(f"Unhandled error in request: {str(e)}")
            
            # Calculate process time even for errors
            process_time = int((time.time() - start_time) * 1000)

            # Create error response
            error_response = {
                "detail": str(e)
            }

            # Log error request to database
            try:
                db = SessionLocal()
                log_entry = RequestLogDB(
                    method=method,
                    path=path,
                    status_code=500,
                    response_time=process_time,
                    request_body=json.dumps(request_data) if request_data else None,
                    response_body=json.dumps(error_response),
                    headers=json.dumps(dict(request.headers)),
                    client_ip=client_ip,
                    user_agent=user_agent
                )
                db.add(log_entry)
                db.commit()
                db.refresh(log_entry)
                
                # Broadcast the log entry
                log_entry.broadcast_log()
                
            except Exception as log_err:
                logger.error(f"Error logging error request: {str(log_err)}")
            finally:
                db.close()
            
            # Re-raise original exception
            raise 

    async def _enhance_request_auth(self, request: Request) -> Request:
        """Enhance request with authentication details"""
        # Check for Authorization header
        auth_header = request.headers.get("Authorization")
        token = None
        
        if auth_header:
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "")
            else:
                # It might be a raw token without Bearer prefix
                token = auth_header
        
        # Also check query parameters if no token found in headers
        if not token and "token" in request.query_params:
            token = request.query_params.get("token")
        
        if token:
            # Try JWT token first
            jwt_payload = verify_token(token)
            if jwt_payload and "sub" in jwt_payload:
                # Handle authenticated user with our JWT
                user_id = jwt_payload["sub"]
                db = SessionLocal()
                try:
                    user = get_user_by_id(db, user_id)
                    if user:
                        # Add user info to request scope for logging
                        request.scope["user_id"] = user.id
                        request.scope["username"] = user.username
                        
                        if user.github_access_token:
                            # If the user has a GitHub token, modify the request to include it
                            # for endpoints that need GitHub API access
                            request.scope["github_token"] = user.github_access_token
                            
                            # Also create a new headers dict with the GitHub token for internal use
                            headers = dict(request.headers)
                            headers["X-GitHub-Token"] = user.github_access_token
                            request.scope["headers"] = [(k.encode(), v.encode()) for k, v in headers.items()]
                finally:
                    db.close()
                    
            else:
                # It might be a GitHub token directly
                # We'll verify it later in the endpoint
                # Just pass it through for now
                request.scope["github_token"] = token
        
        return request

    async def _get_request_body(self, request: Request) -> str:
        """Get the request body for logging"""
        request_body = ""
        if request.method in ["POST", "PUT", "PATCH"]:
            # Save the request body position
            body_position = await request.body()
            # Convert to string for logging
            request_body = body_position.decode() if body_position else ""
            # Reset the request body position
            await request._body.seek(0)
        return request_body

    def _log_request(self, request: Request, response: Response, request_body: str, process_time: float) -> None:
        """Log the request to the database"""
        # Skip logging for static files or health checks
        if request.url.path.startswith("/static") or request.url.path == "/health":
            return
        
        try:
            # Create a new database session
            db = SessionLocal()
            
            # Prepare headers for logging (excluding sensitive ones)
            headers_dict = dict(request.headers.items())
            sanitized_headers = headers_dict.copy()
            
            # Remove sensitive headers like Authorization
            if "Authorization" in sanitized_headers:
                sanitized_headers["Authorization"] = "Bearer [REDACTED]"
            if "Cookie" in sanitized_headers:
                sanitized_headers["Cookie"] = "[REDACTED]"
            
            # Prepare request body for logging (sanitize if needed)
            sanitized_body = self._sanitize_body(request_body)
            
            # Create log entry
            log_entry = RequestLogDB(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                response_time=process_time,
                request_body=sanitized_body,
                response_body="{}", # We don't log response bodies by default
                headers=json.dumps(sanitized_headers),
                client_ip=headers_dict.get("X-Forwarded-For") or request.client.host,
                user_agent=headers_dict.get("User-Agent")
            )
            
            # Add log to database
            db.add(log_entry)
            db.commit()
            
            # Broadcast log via WebSockets if configured
            log_entry.broadcast_log()
            
        except Exception as e:
            logger.error(f"Error logging request: {str(e)}")
        finally:
            db.close()
    
    def _sanitize_body(self, body: str) -> str:
        """Sanitize request body to remove sensitive information"""
        if not body:
            return "{}"
            
        try:
            # Parse the JSON body
            data = json.loads(body)
            
            # Redact sensitive fields
            sensitive_fields = ["password", "token", "secret", "key", "auth"]
            for field in sensitive_fields:
                if field in data:
                    data[field] = "[REDACTED]"
                    
            return json.dumps(data)
        except json.JSONDecodeError:
            # Not a JSON body, return a placeholder
            return json.dumps({"raw_body": "[NON-JSON CONTENT]"})

async def get_token_from_request(request: Request) -> Optional[str]:
    """Extract token from request headers or query parameters.
    
    This function checks multiple sources for the token:
    1. Authorization header (Bearer token)
    2. X-GitHub-Token header (set by middleware)
    3. Query parameters
    4. Token added to request scope by middleware
    """
    # Try to get from Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header:
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "").strip()
        else:
            # It might be a raw token without Bearer prefix
            return auth_header.strip()
    
    # Try to get from X-GitHub-Token header (set by middleware)
    github_token = request.headers.get("X-GitHub-Token")
    if github_token:
        return github_token.strip()
    
    # Try to get from query parameters
    token = request.query_params.get("token")
    if token:
        return token.strip()
    
    # Check if added by middleware
    return request.scope.get("github_token")

async def authenticate_request(request: Request) -> Optional[Dict[str, Any]]:
    """Authenticate a request using either JWT or GitHub token.
    
    This function works in two steps:
    1. First tries to authenticate with JWT token (our system)
    2. If that fails, tries to authenticate with GitHub token
    
    Returns user data if authentication is successful, None otherwise.
    """
    # Get token from various possible sources
    token = await get_token_from_request(request)
    if not token:
        logger.warning("No authentication token found in request")
        return None
    
    # Try JWT token first (our system's token)
    jwt_payload = verify_token(token)
    if jwt_payload and "sub" in jwt_payload:
        # Authenticated with our JWT
        db = SessionLocal()
        try:
            user_id = jwt_payload["sub"]
            user = get_user_by_id(db, user_id)
            if not user:
                logger.warning(f"User not found for ID {user_id}")
                return None
                
            # For endpoints requiring GitHub, use the stored GitHub token
            logger.info(f"Authenticated user: {user.username} via JWT token")
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "github_connected": bool(user.github_id),
                "github_token": user.github_access_token,
                "auth_type": jwt_payload.get("auth_type", "password")
            }
        finally:
            db.close()
    
    # If not a JWT token, try GitHub token
    # Import here to avoid circular imports
    from app.routes.auth import get_github_user
    
    try:
        # Try as GitHub token directly
        github_user = await get_github_user(token)
        if github_user:
            # It's a direct GitHub token
            logger.info(f"Authenticated user: {github_user.get('username')} via GitHub token")
            return github_user
    except Exception as e:
        logger.error(f"Error authenticating with GitHub token: {str(e)}")
    
    logger.warning("Authentication failed: Invalid token")
    return None 