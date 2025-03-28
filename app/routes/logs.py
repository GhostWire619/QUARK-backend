from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
from datetime import datetime, timedelta

from app.database.database import get_db
from app.database.request_log_crud import get_recent_logs
from app.schemas.logs import RequestLogResponse

# Create router
router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/",
    response_model=List[RequestLogResponse],
    summary="Get API request logs",
    description="Retrieves API request logs with optional filtering"
)
async def get_request_logs(
    db: Session = Depends(get_db),
    limit: int = Query(100, description="Maximum number of logs to return", ge=1, le=1000),
    user_id: Optional[str] = Query(None, description="Filter logs by user ID"),
    endpoint: Optional[str] = Query(None, description="Filter logs by endpoint path"),
    hours: Optional[int] = Query(24, description="Get logs from the last N hours")
):
    """
    Get request logs with optional filtering.
    """
    try:
        # Calculate start date if hours is provided
        start_date = None
        if hours:
            start_date = datetime.now() - timedelta(hours=hours)
        
        logs = get_recent_logs(
            db, 
            limit=limit, 
            user_id=user_id, 
            endpoint=endpoint,
            start_date=start_date
        )
        return logs
    except Exception as e:
        logger.error(f"Error retrieving logs: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving logs") 