import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/auth/callback"
FRONTEND_URL = "http://localhost:5173"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
REPOS_FOLDER = os.path.join(os.getcwd(), "repos")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/api/webhook")

# Create repos folder if it doesn't exist
os.makedirs(REPOS_FOLDER, exist_ok=True)