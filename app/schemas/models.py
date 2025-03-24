from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

class WebhookPayload(BaseModel):
    repository: Dict[str, Any] = Field(..., description="Repository information")
    pusher: Optional[Dict[str, Any]] = Field(None, description="Pusher information")
    ref: Optional[str] = Field(None, description="Git reference")

class WebhookEvent(BaseModel):
    id: str = Field(..., min_length=1, description="Event unique identifier")
    type: str = Field(..., min_length=1, description="Event type")
    repository: str = Field(..., min_length=1, description="Repository full name")
    timestamp: str = Field(..., description="Event timestamp")
    payload: Dict[str, Any] = Field(..., description="Event payload")

class RegisteredWebhook(BaseModel):
    id: str = Field(..., min_length=1, description="Webhook unique identifier")
    repository: str = Field(..., min_length=1, description="Repository full name")
    hook_id: str = Field(..., min_length=1, description="GitHub hook ID")
    hook_url: str = Field(..., min_length=1, description="Webhook callback URL")
    events: List[str] = Field(..., min_items=1, description="List of webhook events")
    created_at: str = Field(..., description="Creation timestamp")
    last_synced: str = Field(..., description="Last synchronization timestamp")

# Auth route input models
class AuthCallbackInput(BaseModel):
    code: str = Field(..., min_length=10, description="GitHub OAuth code")

# Webhook route input models
class RepoCommitsInput(BaseModel):
    owner:str = Field(..., min_length=1,description="Repository owner")
    repo: str = Field(...,min_length=1, description="Repository name")
    page: str= Field(1, gt=0,description="Page number for pagination")
    per_page: str= Field(10,gt=0,le=100, description="Items per page")
class SetupWebhookInput(BaseModel):
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")
class WebhookInput(BaseModel):
    event_type: Optional[str] = Field(None, description="GitHub event type")
    payload: Dict[str, Any] = Field(..., description="Webhook payload")


