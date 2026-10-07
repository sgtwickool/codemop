from sqlalchemy import create_engine
from starlette.exceptions import HTTPException
from sqlalchemy.orm import sessionmaker
from app.config import settings
import logging

logger = logging.getLogger(__name__)

def _engine_options(database_url: str) -> dict:
    """Pool options suit a server database; SQLite (local runs, tests) takes none."""
    if database_url.startswith("sqlite"):
        # TestClient and uvicorn may use the connection from another thread
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # Log SQL queries in debug mode
    **_engine_options(settings.DATABASE_URL)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency
def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
        db.commit()  # Commit transaction if successful
    except Exception as e:
        db.rollback()  # Rollback on error
        # HTTP errors (401, 404, 429...) are expected responses, not database failures
        if not isinstance(e, HTTPException):
            logger.error(f"Database transaction failed: {str(e)}")
        raise
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    from app.models.base import Base
    from app.models import pr, suggestion  # noqa: F401 - registers the tables on Base
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("🚀 Database tables initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {str(e)}")
        raise
