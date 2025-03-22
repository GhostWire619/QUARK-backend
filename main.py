import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
import uvicorn


from app.settings import FRONTEND_URL
from app.routes.githubRoutes.auth import router as auth_router
from app.routes.githubRoutes.webhooks import router as webhooks_router
from app.routes.githubRoutes.user import router as user_router
from  app.database.webhook_db import Base

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Create FastAPI app
app = FastAPI(
    title="GitHub Webhook App",
    description="An application for handling GitHub webhooks and OAuth",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# Include routers
app.include_router(auth_router, prefix="/auth")
app.include_router(user_router, prefix="/user")
app.include_router(webhooks_router, prefix="/api")

@app.get("/health")
async def health_check():
    from datetime import datetime
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    uvicorn.run("src.main.app:app", host="0.0.0.0", port=8000, reload=True)