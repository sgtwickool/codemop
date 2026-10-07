from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from app.api.v1.api import api_router
from app.db.session import init_db
from app.config import settings
from app.core.security_config import cors_settings
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.middleware import error_tracking_middleware, request_monitoring_middleware, limit_request_size, add_security_headers
from app.core.monitoring import setup_monitoring
import logging

# Initialize monitoring system
setup_monitoring()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager (modern alternative to on_event)"""
    # Startup: refuse to run without secrets (except in development), then migrate
    for name in settings.check_secrets():
        if name == "GITHUB_WEBHOOK_SECRET":
            logger.warning("⚠️ GITHUB_WEBHOOK_SECRET is not set: webhook signatures are NOT checked (development only)")
        else:
            logger.warning(f"⚠️ {name} is not set: the API that needs it will reject every request")
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

# CORS: only for browser origins explicitly listed in CORS_ORIGINS (none by default)
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, **cors_settings(settings.cors_origins))

# Rate limiting configuration
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Add monitoring middleware
app.middleware("http")(error_tracking_middleware)
app.middleware("http")(request_monitoring_middleware)

# Security middleware (organized in separate module)
app.middleware("http")(limit_request_size)
app.middleware("http")(add_security_headers)

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