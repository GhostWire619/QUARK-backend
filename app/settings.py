import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/api/webhook")
PASSWORD = os.getenv("PASSWORD")
