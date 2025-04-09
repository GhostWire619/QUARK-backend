from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import logging
from app.websockets.logs import log_manager
from app.routes.auth import get_current_user

from app.database.database import get_db, RequestLogDB

# Create router
router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/",
    summary="Get API request logs",
    description="Retrieves all API request logs"
)
async def get_request_logs(
    db: Session = Depends(get_db)
):
    """
    Get all request logs without filtering.
    """
    logs = db.query(RequestLogDB).order_by(RequestLogDB.timestamp.desc()).all()
    
    # Convert SQLAlchemy models to dictionaries
    result = []
    for log in logs:
        log_dict = {
            "id": log.id,
            "endpoint": log.path,
            "method": log.method,
            "status_code": log.status_code,
            "response_time_ms": log.response_time,
            "request_data": log.request_body,
            "response_data": log.response_body,
            "headers": log.headers,
            "timestamp": str(log.timestamp),
            "client_ip": log.client_ip,
            "user_agent": log.user_agent
        }
        result.append(log_dict)
    
    return result

@router.websocket("/ws/logs/{log_id}")
async def websocket_logs(websocket: WebSocket, log_id: str):
    try:
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
        log_manager.disconnect(websocket, log_id)
        raise 