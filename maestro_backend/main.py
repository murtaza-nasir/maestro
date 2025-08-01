from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from concurrent.futures import ThreadPoolExecutor
import asyncio

from database.database import SessionLocal
from database import crud
from api import auth, missions, system, chat, chats, documents, websockets, settings, writing, dashboard, admin
from middleware import user_context_middleware

# Configure reduced logging to minimize console noise
from logging_config import setup_logging
setup_logging()  # Will use LOG_LEVEL environment variable
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MAESTRO API",
    description="AI Research Assistant API",
    version="2.0.0-alpha"
)

# Configure CORS with environment variables
def get_cors_origins():
    """Get CORS allowed origins from environment variables."""
    # Get configurable host and port values
    frontend_host = os.getenv("FRONTEND_HOST", "192.168.68.85")
    frontend_port = os.getenv("FRONTEND_PORT", "3030")
    backend_host = os.getenv("BACKEND_HOST", "192.168.68.85")
    
    # Build default origins using configurable values
    default_origins = [
        "http://localhost:3000",
        "http://localhost:3030",
        "http://localhost:5173",
        f"http://{frontend_host}:{frontend_port}",
        f"http://{backend_host}"
    ]
    
    # Get additional origins from environment variable
    cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if cors_origins_env:
        # Split by comma and strip whitespace
        additional_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
        # Combine with defaults, removing duplicates
        all_origins = list(set(default_origins + additional_origins))
        return all_origins
    
    return default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    # Add max age to reduce preflight requests
    max_age=86400,  # 24 hours
)

# Add user context middleware
app.middleware("http")(user_context_middleware)

# Include API routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(missions.router, prefix="/api", tags=["missions"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(chats.router, prefix="/api", tags=["chats"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(writing.router, tags=["writing"])
app.include_router(websockets.router, tags=["websockets"])
app.include_router(admin.router)

@app.on_event("startup")
async def startup_event():
    """Initialize AI components and create first user on startup."""
    # Only log at ERROR level or higher based on LOG_LEVEL setting
    
    # Create a configurable thread pool
    max_workers = int(os.getenv("MAX_WORKER_THREADS", "10"))
    app.state.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
    
    # Create first user for development if no users exist
    db = SessionLocal()
    try:
        users = crud.get_users(db)
        if not users:
            from setup_first_user import create_first_user
            create_first_user()
    except Exception as e:
        logger.error(f"Error during initial user check: {e}", exc_info=True)
    finally:
        db.close()
    
    # Initialize AI research components
    try:
        from api.missions import initialize_ai_components
        success = initialize_ai_components()
        if not success:
            logger.error("Failed to initialize AI research components")
    except Exception as e:
        logger.error(f"Error during AI component initialization: {e}", exc_info=True)

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    # Only log at ERROR level or higher based on LOG_LEVEL setting
    if hasattr(app.state, "thread_pool"):
        app.state.thread_pool.shutdown(wait=True)

@app.get("/")
def read_root():
    return {
        "message": "MAESTRO API v2.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}
