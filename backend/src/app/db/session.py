from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
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

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# The schema that Base.metadata.create_all() produced before migrations existed
BASELINE_REVISION = "0001"

def alembic_config() -> Config:
    """Alembic config for running migrations from code (no alembic.ini needed)"""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config

def init_db(db_engine=None):
    """Bring the database schema up to date by running any pending migrations"""
    config = alembic_config()
    try:
        with (db_engine or engine).begin() as connection:
            config.attributes["connection"] = connection
            tables = inspect(connection).get_table_names()
            if "prs" in tables and "alembic_version" not in tables:
                logger.info("Database predates migrations; marking it as the baseline schema")
                command.stamp(config, BASELINE_REVISION)
            command.upgrade(config, "head")
        logger.info("🚀 Database schema is up to date")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {str(e)}")
        raise
