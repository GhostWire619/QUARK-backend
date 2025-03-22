from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Table, Integer,create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship ,sessionmaker, scoped_session,Session
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import datetime
import uuid
import logging
import os


# SQLAlchemy setup
Base = declarative_base()
logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite:///webhooks.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base.metadata.create_all(engine)  # Ensure tables are created

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Get current UTC time (timezone-aware)
def get_utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

# Association table for many-to-many relationship between webhooks and events
class WebhookEvent(Base):
    __tablename__ = 'webhook_events'

    webhook_id = Column(String, ForeignKey('registered_webhooks.id'), primary_key=True)
    event_name = Column(String, primary_key=True)

    # Define relationships if necessary
    webhook = relationship("RegisteredWebhook", back_populates="events")

# SQLAlchemy models
class RegisteredWebhookDB(Base):
    __tablename__ = 'registered_webhooks'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    repository = Column(String, nullable=False, index=True)
    hook_id = Column(String, nullable=False, unique=True)
    hook_url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)
    last_synced = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now)
    
    # Relationship to events through association table
    events = relationship('EventDB', secondary=WebhookEvent , backref='webhooks')

class EventDB(Base):
    __tablename__ = 'events'
    
    name = Column(String, primary_key=True)
    description = Column(String, nullable=True)

class WebhookPayloadDB(Base):
    __tablename__ = 'webhook_payloads'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    webhook_id = Column(String, ForeignKey('registered_webhooks.id'))
    repository = Column(JSON, nullable=False)
    pusher = Column(JSON, nullable=True)
    ref = Column(String, nullable=True)
    received_at = Column(DateTime(timezone=True), default=get_utc_now)
    
    webhook = relationship('RegisteredWebhookDB')

# Pydantic models (existing)
class WebhookPayload(BaseModel):
    repository: Dict[str, Any]
    pusher: Optional[Dict[str, Any]] = None
    ref: Optional[str] = None

class RegisteredWebhook(BaseModel):
    id: str
    repository: str
    hook_id: str
    hook_url: str
    events: List[str]
    created_at: str
    last_synced: str

# Database session and CRUD functions
def create_webhook(db_session, repository: str, hook_id: str, hook_url: str, events: List[str]) -> RegisteredWebhookDB:
    """Create a new webhook registration"""
    webhook = RegisteredWebhookDB(
        repository=repository,
        hook_id=hook_id,
        hook_url=hook_url
    )
    
    # Add events
    for event_name in events:
        event = db_session.query(EventDB).filter_by(name=event_name).first()
        if not event:
            event = EventDB(name=event_name)
            db_session.add(event)
        webhook.events.append(event)
    
    db_session.add(webhook)
    db_session.commit()
    return webhook

def log_webhook_payload(db_session, webhook_id: str, payload: WebhookPayload) -> WebhookPayloadDB:
    """Log a received webhook payload"""
    payload_db = WebhookPayloadDB(
        webhook_id=webhook_id,
        repository=payload.repository,
        pusher=payload.pusher,
        ref=payload.ref
    )
    
    db_session.add(payload_db)
    db_session.commit()
    return payload_db

def get_webhook_by_repository(db_session, repository: str) -> List[RegisteredWebhookDB]:
    """Get all webhooks for a repository"""
    return db_session.query(RegisteredWebhookDB).filter_by(repository=repository).all()


def add_webhook_event(db_session: Session, webhook_id: str, event_type: str, payload: dict) -> bool:
    """Add a new webhook event to the database using SQLAlchemy."""
    try:
        event = WebhookPayloadDB(
            webhook_id=webhook_id,
            repository=payload.get("repository", {}),
            pusher=payload.get("pusher"),
            ref=payload.get("ref")
        )
        
        db_session.add(event)
        db_session.commit()
        logger.info(f"Added webhook event: {webhook_id} - {event_type}")
        return True
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Error adding webhook event: {str(e)}")
        return False

def get_webhook_events(db_session: Session):
    """Get all webhook events ordered by timestamp (SQLAlchemy version)."""
    try:
        events = db_session.query(WebhookPayloadDB).order_by(WebhookPayloadDB.received_at.desc()).all()
        return events
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving webhook events: {str(e)}")
        return []

def get_webhook_events_by_repository(db_session: Session, repository: str):
    """Get webhook events filtered by repository."""
    try:
        events = db_session.query(WebhookPayloadDB).filter(WebhookPayloadDB.repository == repository).order_by(WebhookPayloadDB.received_at.desc()).all()
        return events
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving webhook events for {repository}: {str(e)}")
        return []

def clear_webhook_events(db_session: Session) -> bool:
    """Clear all webhook events (for testing purposes)."""
    try:
        num_deleted = db_session.query(WebhookPayloadDB).delete()
        db_session.commit()
        logger.info(f"Cleared {num_deleted} webhook events from database")
        return True
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Error clearing webhook events: {str(e)}")
        return False

def add_or_update_registered_webhook(db_session: Session, repository: str, hook_id: str, hook_url: str, events: list) -> bool:
    """Add or update a registered webhook in the database using SQLAlchemy."""
    try:
        webhook = db_session.query(RegisteredWebhookDB).filter(
            RegisteredWebhookDB.repository == repository,
            RegisteredWebhookDB.hook_id == hook_id
        ).first()

        if webhook:
            webhook.hook_url = hook_url
            webhook.last_synced = get_utc_now()
        else:
            webhook = RegisteredWebhookDB(
                repository=repository,
                hook_id=hook_id,
                hook_url=hook_url
            )
            db_session.add(webhook)

        for event_name in events:
            event = db_session.query(EventDB).filter_by(name=event_name).first()
            if not event:
                event = EventDB(name=event_name)
                db_session.add(event)
            webhook.events.append(event)

        db_session.commit()
        logger.info(f"Webhook {'updated' if webhook else 'added'} for repository: {repository} (hook_id: {hook_id})")
        return True
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Error adding/updating registered webhook: {str(e)}")
        return False

def get_registered_webhooks(db_session: Session):
    """Get all registered webhooks ordered by last sync time."""
    try:
        return db_session.query(RegisteredWebhookDB).order_by(RegisteredWebhookDB.last_synced.desc()).all()
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving registered webhooks: {str(e)}")
        return []

def get_registered_webhooks_by_repository(db_session: Session, repository: str):
    """Get registered webhooks filtered by repository."""
    try:
        return db_session.query(RegisteredWebhookDB).filter_by(repository=repository).order_by(RegisteredWebhookDB.last_synced.desc()).all()
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving registered webhooks for {repository}: {str(e)}")
        return []

def delete_registered_webhook(db_session: Session, repository: str, hook_id: str) -> bool:
    """Delete a registered webhook using SQLAlchemy."""
    try:
        deleted_rows = db_session.query(RegisteredWebhookDB).filter(
            RegisteredWebhookDB.repository == repository,
            RegisteredWebhookDB.hook_id == hook_id
        ).delete()
        db_session.commit()

        if deleted_rows > 0:
            logger.info(f"Deleted registered webhook for {repository} (hook_id: {hook_id})")
            return True
        else:
            logger.warning(f"No registered webhook found for {repository} (hook_id: {hook_id})")
            return False
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Error deleting registered webhook: {str(e)}")
        return False