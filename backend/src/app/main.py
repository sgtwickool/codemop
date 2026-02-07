from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.db.session import init_db
from app.config import settings
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager (modern alternative to on_event)"""
    # Startup: Initialize database
    init_db()
    logger.info("✅ Database initialized")
    yield
    # Shutdown: Cleanup if needed
    logger.info("👋 Application shutdown")

app = FastAPI(
    title="CodeMop API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.HOST if hasattr(settings, 'HOST') else "0.0.0.0",
        port=settings.PORT if hasattr(settings, 'PORT') else 8000,
        log_level="info"
    )