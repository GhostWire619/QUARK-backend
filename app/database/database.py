from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, create_engine, Integer, Boolean, Text, Enum, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import uuid
import logging
from datetime import datetime, timezone
import logging
from enum import Enum as PyEnum
import json
from app.settings import settings
import asyncio
from app.websockets.logs import log_manager

logger = logging.getLogger(__name__)

# SQLAlchemy setup
Base = declarative_base()
DATABASE_URL = "sqlite:///webhooks.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {str(e)}")
        raise
    finally:
        db.close()

# Initialize database tables
def init_db():
    Base.metadata.create_all(engine,)
    logger.info("Database initiated")

def get_utc_now():
    return datetime.now(timezone.utc)


class UserDB(Base):
    __tablename__ = 'users'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    # Relationship to webhooks
    webhooks = relationship('RegisteredWebhookDB', back_populates='user', cascade='all, delete-orphan')
    # Relationship to deployment configs
    deployment_configs = relationship('DeploymentConfigDB', back_populates='user', cascade='all, delete-orphan')
    # Relationship to deployments
    deployments = relationship('DeploymentDB', back_populates='user', cascade='all, delete-orphan')


# SQLAlchemy models
class EventDB(Base):
    __tablename__ = 'events'
    
    name = Column(String, primary_key=True)
    description = Column(String, nullable=True)
    
    # Relationship to webhooks
    webhooks = relationship('RegisteredWebhookDB', secondary='webhook_events', back_populates='events')

class RegisteredWebhookDB(Base):
    __tablename__ = 'registered_webhooks'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    repository = Column(String, nullable=False, index=True)
    hook_id = Column(String, nullable=False, unique=True)
    hook_url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)
    last_synced = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now)

    # Foreign Key: Each webhook belongs to a user
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Relationship to user
    user = relationship('UserDB', back_populates='webhooks')

    # Relationship to events
    events = relationship('EventDB', secondary='webhook_events', back_populates='webhooks')
    
    # Relationship to payloads
    payloads = relationship('WebhookPayloadDB', back_populates='webhook', cascade='all, delete-orphan')


class WebhookPayloadDB(Base):
    __tablename__ = 'webhook_payloads'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    webhook_id = Column(String, ForeignKey('registered_webhooks.id', ondelete='CASCADE'), index=True)
    repository = Column(JSON, nullable=False)
    pusher = Column(JSON, nullable=True)
    ref = Column(String, nullable=True)
    received_at = Column(DateTime(timezone=True), default=get_utc_now, index=True)
    
    # Relationship to webhook
    webhook = relationship('RegisteredWebhookDB', back_populates='payloads')


# Association table for many-to-many relationship
class WebhookEvent(Base):
    __tablename__ = 'webhook_events'

    webhook_id = Column(String, ForeignKey('registered_webhooks.id', ondelete='CASCADE'), primary_key=True)
    event_name = Column(String, ForeignKey('events.name', ondelete='CASCADE'), primary_key=True)


# API Request Logging Model
class RequestLogDB(Base):
    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    method = Column(String)
    path = Column(String)
    status_code = Column(Integer)
    response_time = Column(Float)
    request_body = Column(Text)
    response_body = Column(Text)
    headers = Column(Text)
    client_ip = Column(String)
    user_agent = Column(String, nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "response_time": self.response_time,
            "request_body": json.loads(self.request_body) if self.request_body else None,
            "response_body": json.loads(self.response_body) if self.response_body else None,
            "headers": json.loads(self.headers) if self.headers else None,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent
        }
    
    def broadcast_log(self):
        """Broadcast the log entry to connected WebSocket clients"""
        log_dict = self.to_dict()
        # Broadcast to the "all_logs" channel for clients wanting all logs
        asyncio.create_task(log_manager.broadcast_log("all_logs", log_dict))
        # Also broadcast to path-specific channels
        asyncio.create_task(log_manager.broadcast_log(self.path, log_dict))
        # Keep compatibility with "all" channel
        asyncio.create_task(log_manager.broadcast_log("all", log_dict))


# Deployment Models
class DeploymentStatus(PyEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeploymentEnvironment(PyEnum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "prod"


class DeploymentConfigDB(Base):
    __tablename__ = 'deployment_configs'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    repo_id = Column(String, nullable=False)
    repo_full_name = Column(String, nullable=False, index=True)
    branch = Column(String, nullable=False, default="main")
    auto_deploy = Column(Boolean, default=False)
    deploy_command = Column(String, nullable=False, default="./deploy.sh")
    environment_variables = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now)
    
    # Relationship to user
    user = relationship('UserDB', back_populates='deployment_configs')
    
    # Relationship to deployments
    deployments = relationship('DeploymentDB', back_populates='config', cascade='all, delete-orphan')


class DeploymentDB(Base):
    __tablename__ = 'deployments'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    config_id = Column(String, ForeignKey('deployment_configs.id', ondelete='CASCADE'), nullable=False)
    repo_full_name = Column(String, nullable=False, index=True)
    commit_sha = Column(String, nullable=False)
    branch = Column(String, nullable=False)
    status = Column(String, nullable=False, default=DeploymentStatus.PENDING.value)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    triggered_by = Column(String, nullable=True)
    manual_trigger = Column(Boolean, default=False)
    logs = Column(JSON, nullable=False, default=list)
    error_message = Column(Text, nullable=True)
    
    # Relationship to user
    user = relationship('UserDB', back_populates='deployments')
    
    # Relationship to deployment config
    config = relationship('DeploymentConfigDB', back_populates='deployments')

