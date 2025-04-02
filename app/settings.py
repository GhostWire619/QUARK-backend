from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    # GitHub OAuth settings
    CLIENT_ID: str | None = os.getenv("CLIENT_ID")
    CLIENT_SECRET: str | None = os.getenv("CLIENT_SECRET")
    REDIRECT_URI: str = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")
    
    # Application URLs
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "http://localhost:8000/api/webhook")
    
    # Security
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
    PASSWORD: str | None = os.getenv("PASSWORD")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()
