from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeploymentEnvironment(str, Enum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "prod"


class DeploymentConfig(BaseModel):
    """Configuration for repository deployment settings"""
    repo_id: int
    repo_full_name: str
    branch: str = "main"
    auto_deploy: bool = False
    deploy_command: str = "./deploy.sh"
    environment_variables: Optional[Dict[str, str]] = Field(
        default={},
        description="Environment variables to be used during deployment"
    )


class DeploymentRequest(BaseModel):
    """Request to create a new deployment"""
    repo_full_name: str
    commit_sha: str
    branch: str
    manual_trigger: bool = False
    triggered_by: Optional[str] = None


class Deployment(BaseModel):
    """Deployment record"""
    id: str = Field(..., description="Unique deployment ID")
    repo_full_name: str
    commit_sha: str
    branch: str
    status: DeploymentStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    triggered_by: Optional[str] = None
    manual_trigger: bool = False
    logs: List[str] = []
    error_message: Optional[str] = None


class DeploymentResult(BaseModel):
    """Result of a deployment operation"""
    deployment_id: str
    status: DeploymentStatus
    message: str
    logs_url: Optional[str] = None 