from pydantic import BaseModel, Field, constr, conint
from typing import Dict, Any, Optional, List
from datetime import datetime

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
    code: str = Field(..., min_length=20, description="GitHub OAuth code")

# User route input models
class UserProfileInput(BaseModel):
    token: Optional[str] = Field(None, min_length=40, description="GitHub access token")

class UserReposInput(BaseModel):
    token: Optional[str] = Field(None, min_length=40, description="GitHub access token")

# Webhook route input models
class RepoCommitsInput(BaseModel):
    owner: constr(min_length=1) = Field(..., description="Repository owner")
    repo: constr(min_length=1) = Field(..., description="Repository name")
    page: conint(gt=0) = Field(1, description="Page number for pagination")
    per_page: conint(gt=0, le=100) = Field(10, description="Items per page")
    token: Optional[str] = Field(None, min_length=40, description="GitHub access token")

class SetupWebhookInput(BaseModel):
    owner: constr(min_length=1) = Field(..., description="Repository owner")
    repo: constr(min_length=1) = Field(..., description="Repository name")
    token: Optional[str] = Field(None, min_length=40, description="GitHub access token")

class WebhookInput(BaseModel):
    event_type: Optional[str] = Field(None, description="GitHub event type")
    payload: Dict[str, Any] = Field(..., description="Webhook payload")