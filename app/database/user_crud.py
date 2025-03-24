from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

from sqlalchemy.orm import  Session
from .database import UserDB
from app.schemas.user_models import (UserCreate,UserUpdate)


def get_users(db: Session):
    """Retrieve all users."""
    return db.query(UserDB).all()

def get_user_by_id(db: Session, user_id: str):
    """Retrieve a user by ID."""
    return db.query(UserDB).filter(UserDB.id == user_id).first()

def create_user(db: Session, user_data: UserCreate):
    """Create a new user."""
    user = db.query(UserDB).filter(UserDB.username == user_data.username).first()
    if user:
        return None
    new_user = UserDB(
        id=str(uuid.uuid4()),
        username=user_data.username,
        email=user_data.email,
        password_hash=generate_password_hash(user_data.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
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




