import time
import json
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import iterate_in_threadpool
from sqlalchemy.orm import Session
from app.database.database import get_db, RequestLogDB

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
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

        # Try to extract GitHub token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        github_token = None
        if auth_header.startswith("Bearer "):
            github_token = auth_header.replace("Bearer ", "")
            # Set a placeholder user identifier for logged requests when only token is available
            if not user_id and github_token:
                user_id = "authenticated-user"  # This will be replaced with actual user ID later if possible
                # Log the GitHub token for debugging
                logger.info(f"GitHub Token: {github_token}")
        
        # If no user identified yet, use client IP as identifier
        if not user_id:
            user_id = f"anon-{client_ip}" if client_ip else "unknown-user"
        
        # Extract query parameters for additional context
        query_params = dict(request.query_params)
        if query_params and not request_data:
            # Include all parameters without masking
            request_data = {"query_params": query_params}
        
        # Try to capture request body for POST/PUT/PATCH requests
        try:
            if method in ["POST", "PUT", "PATCH"] and request.headers.get("content-type") == "application/json":
                # Clone the request body stream
                body_bytes = await request.body()
                
                # Create a new request with the same body data for processing
                request = Request(
                    scope=request.scope,
                    receive=request._receive,
                )
                
                # Parse request data (limiting size for security)
                try:
                    if len(body_bytes) <= 10_000:  # Limit to 10KB
                        body_json = json.loads(body_bytes)
                        
                        # Include all data without masking
                        if request_data and "query_params" in request_data:
                            request_data["body"] = body_json
                        else:
                            request_data = body_json
                except:
                    request_data = {"error": "Could not parse request body"}
        except Exception as e:
            logger.error(f"Error capturing request data: {str(e)}")
            
        # Process the request
        try:
            response = await call_next(request)
            status_code = response.status_code
            
            # Try to extract real user info from the response
            if user_id == "authenticated-user" and hasattr(response, "user_id"):
                user_id = response.user_id
                username = getattr(response, "username", None)
            
            # Calculate request processing time
            process_time = int((time.time() - start_time) * 1000)
            
            # Add additional context for specific endpoints
            if path.startswith("/auth/") and status_code == 200:
                if path == "/auth/login" or path == "/auth/callback":
                    # Track successful authentication attempts
                    logger.info(f"Authentication attempt from {client_ip} ({user_agent})")
                    if github_token:
                        logger.info(f"GitHub Token: {github_token}")
            
            # Log request to database in a non-blocking way
            try:
                # Get DB session from generator
                for db in get_db():
                    # Create log entry
                    log_entry = RequestLogDB(
                        endpoint=path,
                        method=method,
                        user_id=user_id,
                        username=username,
                        status_code=status_code,
                        request_data=request_data,
                        response_time_ms=process_time,
                        client_ip=client_ip,
                        user_agent=user_agent
                    )
                    db.add(log_entry)
                    db.commit()
                    break
            except Exception as e:
                logger.error(f"Error logging request to database: {str(e)}")
            
            # Add processing time header
            response.headers["X-Process-Time"] = str(process_time)
            return response
            
        except Exception as e:
            # Log unhandled exceptions
            logger.error(f"Unhandled error in request: {str(e)}")
            
            # Calculate process time even for errors
            process_time = int((time.time() - start_time) * 1000)
            
            # Log error request to database
            try:
                # Get DB session from generator
                for db in get_db():
                    # Create log entry
                    log_entry = RequestLogDB(
                        endpoint=path,
                        method=method,
                        user_id=user_id,
                        username=username,
                        status_code=500,
                        request_data=request_data,
                        response_time_ms=process_time,
                        client_ip=client_ip,
                        user_agent=user_agent
                    )
                    db.add(log_entry)
                    db.commit()
                    break
            except Exception as log_err:
                logger.error(f"Error logging error request to database: {str(log_err)}")
            
            # Re-raise original exception
            raise e 