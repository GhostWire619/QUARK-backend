from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class RequestLogResponse(BaseModel):
    id: str
    endpoint: str
    method: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    status_code: Optional[int] = None
    request_data: Optional[Dict[str, Any]] = None
    response_time_ms: Optional[int] = None
    timestamp: datetime
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    
    class Config:
        from_attributes = True 