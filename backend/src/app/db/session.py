from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.config import settings
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=settings.DEBUG  # Log SQL queries in debug mode
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
        logger.error(f"Database transaction failed: {str(e)}")
        raise
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    from app.models.base import Base
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("🚀 Database tables initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {str(e)}")
        raise

# Async database support (for future use)
# Note: Requires asyncpg driver instead of psycopg2
# async_engine = create_async_engine(
#     settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
# )
# AsyncSessionLocal = sessionmaker(
#     async_engine,
#     expire_on_commit=False,
#     class_=AsyncSession
# )

# async def get_async_db():
#     """Async database session dependency"""
#     async with AsyncSessionLocal() as session:
#         try:
#             yield session
#             await session.commit()
#         except Exception as e:
#             await session.rollback()
#             logger.error(f"Async database transaction failed: {str(e)}")
#             raise