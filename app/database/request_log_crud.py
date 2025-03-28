from sqlalchemy.orm import Session
import logging
from sqlalchemy import func, desc
from app.database.database import RequestLogDB
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def create_request_log(
    db: Session,
    endpoint: str,
    method: str,
    user_id: str = None,
    username: str = None,
    status_code: int = None,
    request_data: dict = None,
    response_time_ms: int = None,
    client_ip: str = None,
    user_agent: str = None
):
    """
    Create a new request log entry in the database
    """
    try:
        log_entry = RequestLogDB(
            endpoint=endpoint,
            method=method,
            user_id=user_id,
            username=username,
            status_code=status_code,
            request_data=request_data,
            response_time_ms=response_time_ms,
            client_ip=client_ip,
            user_agent=user_agent
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception as e:
        logger.error(f"Error creating request log: {str(e)}")
        return None

def get_recent_logs(
    db: Session,
    limit: int = 100,
    user_id: str = None,
    endpoint: str = None,
    start_date: datetime = None,
    end_date: datetime = None
):
    """
    Get recent logs, optionally filtered by various parameters
    """
    query = db.query(RequestLogDB).order_by(RequestLogDB.timestamp.desc())
    
    if user_id:
        query = query.filter(RequestLogDB.user_id == user_id)
    
    if endpoint:
        query = query.filter(RequestLogDB.endpoint.contains(endpoint))
    
    if start_date:
        query = query.filter(RequestLogDB.timestamp >= start_date)
    
    if end_date:
        query = query.filter(RequestLogDB.timestamp <= end_date)
    
    return query.limit(limit).all()

def get_logs_by_endpoint(
    db: Session,
    endpoint: str,
    limit: int = 100,
    start_date: datetime = None,
    end_date: datetime = None
):
    """
    Get logs for a specific endpoint
    """
    query = db.query(RequestLogDB)\
        .filter(RequestLogDB.endpoint == endpoint)\
        .order_by(RequestLogDB.timestamp.desc())
    
    if start_date:
        query = query.filter(RequestLogDB.timestamp >= start_date)
    
    if end_date:
        query = query.filter(RequestLogDB.timestamp <= end_date)
    
    return query.limit(limit).all()

def get_logs_by_user(
    db: Session,
    user_id: str,
    limit: int = 100,
    start_date: datetime = None,
    end_date: datetime = None
):
    """
    Get logs for a specific user
    """
    query = db.query(RequestLogDB)\
        .filter(RequestLogDB.user_id == user_id)\
        .order_by(RequestLogDB.timestamp.desc())
    
    if start_date:
        query = query.filter(RequestLogDB.timestamp >= start_date)
    
    if end_date:
        query = query.filter(RequestLogDB.timestamp <= end_date)
    
    return query.limit(limit).all()

def get_endpoint_stats(
    db: Session,
    days: int = 7,
    limit: int = 10
):
    """
    Get statistics about most accessed endpoints
    """
    start_date = datetime.now() - timedelta(days=days)
    
    stats = db.query(
        RequestLogDB.endpoint,
        func.count(RequestLogDB.id).label('count'),
        func.avg(RequestLogDB.response_time_ms).label('avg_response_time')
    )\
    .filter(RequestLogDB.timestamp >= start_date)\
    .group_by(RequestLogDB.endpoint)\
    .order_by(desc('count'))\
    .limit(limit)\
    .all()
    
    return stats

def get_error_logs(
    db: Session,
    limit: int = 100,
    days: int = 7
):
    """
    Get logs for requests that resulted in error status codes (4xx, 5xx)
    """
    start_date = datetime.now() - timedelta(days=days)
    
    return db.query(RequestLogDB)\
        .filter(RequestLogDB.timestamp >= start_date)\
        .filter(RequestLogDB.status_code >= 400)\
        .order_by(RequestLogDB.timestamp.desc())\
        .limit(limit)\
        .all()

def get_slow_requests(
    db: Session,
    min_time_ms: int = 500,
    limit: int = 100,
    days: int = 7
):
    """
    Get logs for slow requests
    """
    start_date = datetime.now() - timedelta(days=days)
    
    return db.query(RequestLogDB)\
        .filter(RequestLogDB.timestamp >= start_date)\
        .filter(RequestLogDB.response_time_ms >= min_time_ms)\
        .order_by(RequestLogDB.response_time_ms.desc())\
        .limit(limit)\
        .all() 