from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import logging

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
            "endpoint": log.endpoint,
            "method": log.method,
            "user_id": log.user_id,
            "username": log.username,
            "status_code": log.status_code,
            "request_data": log.request_data,
            "response_time_ms": log.response_time_ms,
            "timestamp": str(log.timestamp),
            "client_ip": log.client_ip,
            "user_agent": log.user_agent
        }
        result.append(log_dict)
    
    return result 