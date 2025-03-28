from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, create_engine, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import uuid
import logging
import datetime
import logging

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
    return datetime.datetime.now(datetime.timezone.utc)


class UserDB(Base):
    __tablename__ = 'users'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    # Relationship to webhooks
    webhooks = relationship('RegisteredWebhookDB', back_populates='user', cascade='all, delete-orphan')


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
    __tablename__ = 'request_logs'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    endpoint = Column(String, nullable=False, index=True)
    method = Column(String, nullable=False)
    user_id = Column(String, nullable=True, index=True)
    username = Column(String, nullable=True)
    status_code = Column(Integer, nullable=True)
    request_data = Column(JSON, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=get_utc_now, index=True)
    client_ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

