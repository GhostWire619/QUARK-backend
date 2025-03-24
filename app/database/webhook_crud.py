from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import List
import logging

from .database import (RegisteredWebhookDB,EventDB,get_utc_now,WebhookPayloadDB)
from app.schemas.models import WebhookPayload

# Setup logging
logger = logging.getLogger(__name__)

# Database CRUD operations
def create_webhook(db_session: Session, repository: str, hook_id: str, hook_url: str, events: List[str]) -> RegisteredWebhookDB:
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
        
        # Clear existing events first
        webhook.events = []
        webhook.events.append(event)
    
    db_session.add(webhook)
    db_session.commit()
    return webhook

def log_webhook_payload(db_session: Session, webhook_id: str, payload: WebhookPayload) -> WebhookPayloadDB:
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

def get_webhook_by_repository(db_session: Session, repository: str) -> List[RegisteredWebhookDB]:
    """Get all webhooks for a repository"""
    return db_session.query(RegisteredWebhookDB).filter_by(repository=repository).all()

def add_webhook_event(db_session: Session, webhook_id: str, event_type: str, payload: dict) -> bool:
    """Add a new webhook event to the database"""
    try:
        event = WebhookPayloadDB(
            webhook_id=webhook_id,
            repository=payload.get("repository", {}),
            pusher=payload.get("sender", {}),
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

def get_webhook_events(db_session: Session, limit: int = 100):
    """Get all webhook events ordered by timestamp with limit"""
    try:
        return db_session.query(WebhookPayloadDB).order_by(
            WebhookPayloadDB.received_at.desc()
        ).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving webhook events: {str(e)}")
        return []

def get_webhook_events_by_repository(db_session: Session, repository: str, limit: int = 100):
    """Get webhook events filtered by repository with limit"""
    try:
        # Using JSON filtering appropriate for SQLite
        return db_session.query(WebhookPayloadDB).filter(
            WebhookPayloadDB.repository.like(f'%"{repository}"%')
        ).order_by(WebhookPayloadDB.received_at.desc()).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving webhook events for {repository}: {str(e)}")
        return []

def clear_webhook_events(db_session: Session) -> bool:
    """Clear all webhook events (for testing purposes)"""
    try:
        num_deleted = db_session.query(WebhookPayloadDB).delete()
        db_session.commit()
        logger.info(f"Cleared {num_deleted} webhook events from database")
        return True
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Error clearing webhook events: {str(e)}")
        return False

def add_or_update_registered_webhook(db_session: Session, repository: str, hook_id: str, hook_url: str, events: List[str]) -> bool:
    """Add or update a registered webhook in the database"""
    try:
        webhook = db_session.query(RegisteredWebhookDB).filter_by(hook_id=hook_id).first()

        if webhook:
            webhook.repository = repository
            webhook.hook_url = hook_url
            webhook.last_synced = get_utc_now()
            
            # Clear existing events
            webhook.events = []
        else:
            webhook = RegisteredWebhookDB(
                repository=repository,
                hook_id=hook_id,
                hook_url=hook_url
            )
            db_session.add(webhook)

        # Add events
        for event_name in events:
            event = db_session.query(EventDB).filter_by(name=event_name).first()
            if not event:
                event = EventDB(name=event_name)
                db_session.add(event)
            webhook.events.append(event)

        db_session.commit()
        action = "updated" if webhook.id else "added"
        logger.info(f"Webhook {action} for repository: {repository} (hook_id: {hook_id})")
        return True
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Error adding/updating webhook: {str(e)}")
        return False

def get_registered_webhooks(db_session: Session, limit: int = 100):
    """Get all registered webhooks ordered by last sync time with limit"""
    try:
        return db_session.query(RegisteredWebhookDB).order_by(
            RegisteredWebhookDB.last_synced.desc()
        ).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving webhooks: {str(e)}")
        return []

def get_registered_webhooks_by_repository(db_session: Session, repository: str):
    """Get registered webhooks filtered by repository"""
    try:
        return db_session.query(RegisteredWebhookDB).filter_by(
            repository=repository
        ).order_by(RegisteredWebhookDB.last_synced.desc()).all()
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving webhooks for {repository}: {str(e)}")
        return []

def delete_registered_webhook(db_session: Session, repository: str, hook_id: str) -> bool:
    """Delete a registered webhook"""
    try:
        webhook = db_session.query(RegisteredWebhookDB).filter(
            RegisteredWebhookDB.repository == repository,
            RegisteredWebhookDB.hook_id == hook_id
        ).first()
        
        if webhook:
            db_session.delete(webhook)
            db_session.commit()
            logger.info(f"Deleted webhook for {repository} (hook_id: {hook_id})")
            return True
        else:
            logger.warning(f"No webhook found for {repository} (hook_id: {hook_id})")
            return False
    except SQLAlchemyError as e:
        db_session.rollback()
        logger.error(f"Error deleting webhook: {str(e)}")
        return False
