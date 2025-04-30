from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from sqlalchemy import and_
from datetime import datetime
import logging
from typing import Optional, Union, Dict, Any

from sqlalchemy.orm import Session
from .database import UserDB
from app.schemas.user_models import UserUpdate

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

def get_user_by_github_id(db: Session, github_id: str) -> Optional[UserDB]:
    """Get a user by their GitHub ID"""
    return db.query(UserDB).filter(UserDB.github_id == github_id).first()

def verify_password(user: UserDB, password: str) -> bool:
    """Verify a user's password"""
    if not user.password_hash:
        return False
    return check_password_hash(user.password_hash, password)

def create_user(db: Session, user_data: Union[Dict[str, Any], tuple[str, str, Optional[str]], Any]) -> Optional[UserDB]:
    """Create a new user.
    
    Args:
        db: Database session
        user_data: Either a dict, a tuple of (username, email, password), or a Pydantic model
    """
    # Convert input to dict if necessary
    if isinstance(user_data, tuple):
        username, email, password = user_data
        username_value = username
        email_value = email
        password_value = password or ""
    elif isinstance(user_data, dict):
        username_value = user_data["username"]
        email_value = user_data["email"]
        password_value = user_data.get("password", "")
    else:
        # Handle Pydantic model (has attributes instead of dict keys)
        username_value = user_data.username
        email_value = user_data.email
        password_value = getattr(user_data, "password", "")

    # Check if user already exists
    existing_user = db.query(UserDB).filter(
        (UserDB.username == username_value) | (UserDB.email == email_value)
    ).first()
    
    if existing_user:
        # Update the existing user's information if needed
        if password_value:
            existing_user.password_hash = generate_password_hash(password_value)
        db.commit()
        return existing_user

    # Create new user
    new_user = UserDB(
        id=str(uuid.uuid4()),
        username=username_value,
        email=email_value,
        password_hash=generate_password_hash(password_value) if password_value else None
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

def link_github_account(db: Session, user_id: str, github_data: Dict[str, Any]) -> Optional[UserDB]:
    """Link a GitHub account to an existing user
    
    Args:
        db: Database session
        user_id: User ID to link with
        github_data: GitHub user data including github_id, username, etc.
    """
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        return None
    
    # Update user with GitHub information
    user.github_id = str(github_data.get("id"))
    user.github_username = github_data.get("login")
    user.github_access_token = github_data.get("token")
    user.github_avatar_url = github_data.get("avatar_url")
    
    db.commit()
    db.refresh(user)
    logger.info(f"Linked GitHub account {github_data.get('login')} to user {user.username}")
    return user

def create_or_update_github_user(db: Session, github_data: Dict[str, Any]) -> UserDB:
    """Create or update a user from GitHub data
    
    Args:
        db: Database session
        github_data: GitHub user data
    """
    github_id = str(github_data.get("id"))
    
    # Check if user already exists with this GitHub ID
    existing_user = get_user_by_github_id(db, github_id)
    if existing_user:
        # Update GitHub token and other info
        existing_user.github_access_token = github_data.get("token")
        existing_user.github_avatar_url = github_data.get("avatar_url")
        if github_data.get("login") and github_data.get("login") != existing_user.github_username:
            existing_user.github_username = github_data.get("login")
        
        db.commit()
        db.refresh(existing_user)
        return existing_user
    
    # Check if user exists with the same email
    email = github_data.get("email") or f"{github_data.get('login')}@github.com"
    existing_user = get_user_by_email(db, email)
    if existing_user:
        # Link GitHub account to existing user
        return link_github_account(db, existing_user.id, github_data)
    
    # Create new user with GitHub data
    new_user = UserDB(
        id=str(uuid.uuid4()),
        username=github_data.get("login"),
        email=email,
        github_id=github_id,
        github_username=github_data.get("login"),
        github_access_token=github_data.get("token"),
        github_avatar_url=github_data.get("avatar_url")
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    logger.info(f"Created new user from GitHub: {new_user.username}")
    return new_user

def delete_user(db: Session, user_id: str):
    """Delete a user."""
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        return None

    db.delete(user)
    db.commit()
    return True




