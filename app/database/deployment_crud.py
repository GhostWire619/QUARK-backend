from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
import uuid
import logging
from typing import List, Optional, Dict, Any

from app.database.database import DeploymentConfigDB, DeploymentDB, DeploymentStatus, DeploymentEnvironment
from app.schemas.deployment_models import DeploymentConfig, DeploymentRequest, Deployment, DeploymentResult

logger = logging.getLogger(__name__)


# Deployment Configuration CRUD Operations
def create_deployment_config(db: Session, user_id: str, config: DeploymentConfig) -> DeploymentConfigDB:
    """Create a new deployment configuration for a repository"""
    db_config = DeploymentConfigDB(
        user_id=user_id,
        repo_id=config.repo_id,
        repo_full_name=config.repo_full_name,
        branch=config.branch,
        auto_deploy=config.auto_deploy,
        deploy_command=config.deploy_command,
        environment_variables=config.environment_variables
    )
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    logger.info(f"Created deployment config for {config.repo_full_name}")
    return db_config


def get_deployment_config(db: Session, repo_full_name: str, user_id: str) -> Optional[DeploymentConfigDB]:
    """Get deployment configuration for a repository"""
    return db.query(DeploymentConfigDB).filter(
        and_(
            DeploymentConfigDB.repo_full_name == repo_full_name,
            DeploymentConfigDB.user_id == user_id
        )
    ).first()


def update_deployment_config(db: Session, config_id: str, config_data: Dict[str, Any]) -> Optional[DeploymentConfigDB]:
    """Update an existing deployment configuration"""
    db_config = db.query(DeploymentConfigDB).filter(DeploymentConfigDB.id == config_id).first()
    if not db_config:
        return None
    
    # Update configuration fields
    for key, value in config_data.items():
        if hasattr(db_config, key):
            setattr(db_config, key, value)
    
    db.commit()
    db.refresh(db_config)
    logger.info(f"Updated deployment config {config_id}")
    return db_config


def delete_deployment_config(db: Session, config_id: str, user_id: str) -> bool:
    """Delete a deployment configuration"""
    result = db.query(DeploymentConfigDB).filter(
        and_(
            DeploymentConfigDB.id == config_id,
            DeploymentConfigDB.user_id == user_id
        )
    ).delete()
    db.commit()
    logger.info(f"Deleted deployment config {config_id}")
    return result > 0


def list_deployment_configs(db: Session, user_id: str) -> List[DeploymentConfigDB]:
    """List all deployment configurations for a user"""
    return db.query(DeploymentConfigDB).filter(DeploymentConfigDB.user_id == user_id).all()


# Deployment CRUD Operations
def create_deployment(db: Session, user_id: str, request: DeploymentRequest) -> Optional[DeploymentDB]:
    """Create a new deployment"""
    # Get deployment config
    config = get_deployment_config(db, request.repo_full_name, user_id)
    if not config:
        logger.error(f"No deployment config found for {request.repo_full_name}")
        return None
    
    # Create deployment
    deployment = DeploymentDB(
        id=str(uuid.uuid4()),
        user_id=user_id,
        config_id=config.id,
        repo_full_name=request.repo_full_name,
        commit_sha=request.commit_sha,
        branch=request.branch,
        status=DeploymentStatus.PENDING.value,
        created_at=datetime.now(),
        triggered_by=request.triggered_by,
        manual_trigger=request.manual_trigger,
        logs=[]
    )
    
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    logger.info(f"Created deployment {deployment.id} for {request.repo_full_name}")
    return deployment


def get_deployment(db: Session, deployment_id: str) -> Optional[DeploymentDB]:
    """Get a deployment by ID"""
    return db.query(DeploymentDB).filter(DeploymentDB.id == deployment_id).first()


def list_deployments(db: Session, repo_full_name: Optional[str] = None, user_id: Optional[str] = None, 
                    limit: int = 10, offset: int = 0) -> List[DeploymentDB]:
    """List deployments with optional filtering"""
    query = db.query(DeploymentDB)
    
    if repo_full_name:
        query = query.filter(DeploymentDB.repo_full_name == repo_full_name)
    
    if user_id:
        query = query.filter(DeploymentDB.user_id == user_id)
    
    return query.order_by(DeploymentDB.created_at.desc()).limit(limit).offset(offset).all()


def update_deployment_status(db: Session, deployment_id: str, status: DeploymentStatus, 
                             logs: Optional[List[str]] = None, error_message: Optional[str] = None) -> Optional[DeploymentDB]:
    """Update deployment status and logs"""
    deployment = get_deployment(db, deployment_id)
    if not deployment:
        logger.error(f"Deployment {deployment_id} not found")
        return None
    
    deployment.status = status.value
    
    if status == DeploymentStatus.IN_PROGRESS and not deployment.started_at:
        deployment.started_at = datetime.now()
    
    if status in [DeploymentStatus.COMPLETED, DeploymentStatus.FAILED, DeploymentStatus.CANCELLED]:
        deployment.completed_at = datetime.now()
    
    if logs:
        current_logs = deployment.logs or []
        deployment.logs = current_logs + logs
    
    if error_message:
        deployment.error_message = error_message
    
    db.commit()
    db.refresh(deployment)
    logger.info(f"Updated deployment {deployment_id} status to {status.value}")
    return deployment


def add_deployment_log(db: Session, deployment_id: str, log_message: str) -> Optional[DeploymentDB]:
    """Add a log message to a deployment"""
    deployment = get_deployment(db, deployment_id)
    if not deployment:
        logger.error(f"Deployment {deployment_id} not found")
        return None
    
    # Add log message
    timestamp = datetime.now().isoformat()
    log_entry = f"[{timestamp}] {log_message}"
    
    if isinstance(deployment.logs, list):
        deployment.logs.append(log_entry)
    else:
        deployment.logs = [log_entry]
    
    db.commit()
    db.refresh(deployment)
    return deployment


def delete_deployment(db: Session, deployment_id: str, user_id: str) -> bool:
    """Delete a deployment record
    
    This permanently removes a deployment record from the database.
    """
    result = db.query(DeploymentDB).filter(
        and_(
            DeploymentDB.id == deployment_id,
            DeploymentDB.user_id == user_id
        )
    ).delete()
    db.commit()
    logger.info(f"Deleted deployment {deployment_id}")
    return result > 0 