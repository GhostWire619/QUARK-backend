from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from sqlalchemy import and_
from datetime import datetime
import logging
from typing import Optional, Union, Dict, Any

from sqlalchemy.orm import  Session
from .database import UserDB
from app.schemas.user_models import (UserCreate,UserUpdate)

logger = logging.getLogger(__name__)

def get_users(db: Session):
    """Retrieve all users."""
    return db.query(UserDB).all()

def get_user_by_id(db: Session, user_id: str):
    """Retrieve a user by ID."""
    return db.query(UserDB).filter(UserDB.id == user_id).first()

def get_user_by_email(db: Session, email: str) -> Optional[UserDB]:
    """Get a user by their email address"""
    return db.query(UserDB).filter(UserDB.email == email).first()

def create_user(db: Session, user_data: Union[UserCreate, tuple[str, str, Optional[str]], Dict[str, Any]]) -> Optional[UserDB]:
    """Create a new user.
    
    Args:
        db: Database session
        user_data: Either a UserCreate model, a tuple of (username, email, password), or a dict
    """
    # Convert input to UserCreate if necessary
    if isinstance(user_data, tuple):
        username, email, password = user_data
        user_data = UserCreate(username=username, email=email, password=password or "")
    elif isinstance(user_data, dict):
        user_data = UserCreate(**user_data)

    # Check if user already exists
    existing_user = db.query(UserDB).filter(
        (UserDB.username == user_data.username) | (UserDB.email == user_data.email)
    ).first()
    
    if existing_user:
        # Update the existing user's information if needed
        if user_data.password:
            existing_user.password_hash = generate_password_hash(user_data.password)
        db.commit()
        return existing_user

    # Create new user
    new_user = UserDB(
        id=str(uuid.uuid4()),
        username=user_data.username,
        email=user_data.email,
        password_hash=generate_password_hash(user_data.password) if user_data.password else None
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    logger.info(f"Created new user: {new_user.username}")
    return new_user

def update_user(db: Session, user_id: str, user_data: UserUpdate):
    """Update user details."""
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        return None
    
    if user_data.username:
        user.username = user_data.username
    if user_data.email:
        user.email = user_data.email
    if user_data.password:
        user.password_hash = generate_password_hash(user_data.password)
    
    db.commit()
    db.refresh(user)
    return user

def delete_user(db: Session, user_id: str):
    """Delete a user."""
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        return None

    db.delete(user)
    db.commit()
    return True




