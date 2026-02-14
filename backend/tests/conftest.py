"""
Pytest configuration and fixtures for CodeMop backend tests.
"""
import pytest
import sys
import os
from fastapi.testclient import TestClient

# Add src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from app.main import app
from app.db.session import get_db, init_db
from app.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Test database configuration - use file-based SQLite to avoid thread issues
TEST_DATABASE_URL = "sqlite:///./test.db"

# Create test engine and session BEFORE importing anything
import sys
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

# Create test engine and session with thread-safe configuration
# Use check_same_thread=False to allow connections across threads
# Use connect_args to configure SQLite for better concurrency
connect_args = {"check_same_thread": False}
if "sqlite" in TEST_DATABASE_URL:
    test_engine = create_engine(TEST_DATABASE_URL, connect_args=connect_args)
else:
    test_engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Override the database engine for testing BEFORE importing the app
import app.db.session as db_session_module
original_engine = db_session_module.engine
db_session_module.engine = test_engine

# Also override the SessionLocal to use the test engine
db_session_module.SessionLocal = TestSessionLocal

# Verify the override worked
print(f"Test database configured: {test_engine}")

# Store original engine for restoration at session end
original_engine_for_restore = db_session_module.engine
original_session_local_for_restore = db_session_module.SessionLocal

@pytest.fixture(scope="session", autouse=True)
def setup_test_database_engine():
    """Set up test database engine for entire test session."""
    # This fixture runs once per test session
    yield
    # Restore original engine at the end of the session
    db_session_module.engine = original_engine_for_restore
    db_session_module.SessionLocal = original_session_local_for_restore
    print(f"Restored original engine at session end")

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    # Create all tables
    Base.metadata.create_all(bind=test_engine)
    
    # Create session
    session = TestSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=test_engine)

@pytest.fixture(scope="function")
def client():
    """Create a test client for the FastAPI app with test database."""
    # Initialize test database
    Base.metadata.create_all(bind=test_engine)
    
    # Import and create test client
    from app.main import app as fastapi_app
    
    # Create test client
    test_client = TestClient(fastapi_app)
    
    yield test_client
    
    # Clean up
    Base.metadata.drop_all(bind=test_engine)
    
    # Note: Don't restore original engine here to allow multiple calls within same test
    # Engine restoration is handled at the end of the entire test session

@pytest.fixture(scope="function")
def test_app():
    """Create a test instance of the FastAPI app."""
    return app

@pytest.fixture(scope="function")
def github_webhook_payload():
    """Standard GitHub webhook payload for testing."""
    return {
        "action": "opened",
        "number": 123,
        "pull_request": {
            "title": "Test PR",
            "user": {"login": "testuser"},
            "head": {"ref": "test-branch"},
            "html_url": "https://github.com/testuser/testrepo/pull/123",
            "diff_url": "https://github.com/testuser/testrepo/pull/123.diff"
        },
        "repository": {
            "name": "testrepo",
            "full_name": "testuser/testrepo"
        }
    }

@pytest.fixture(scope="function")
def github_signature():
    """Generate a valid GitHub webhook signature using the actual secret."""
    import hmac
    import hashlib
    import json
    from app.config import settings
    
    def generate_signature(payload):
        body = json.dumps(payload)
        # Use the actual webhook secret from settings
        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        return "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
    
    return generate_signature

@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    # Save original environment variables
    original_env = {
        "GITHUB_WEBHOOK_SECRET": os.environ.get("GITHUB_WEBHOOK_SECRET"),
        "AI_API_KEY": os.environ.get("AI_API_KEY"),
        "API_KEY": os.environ.get("API_KEY")
    }
    
    # Set test environment variables
    os.environ["GITHUB_WEBHOOK_SECRET"] = "test_secret"
    os.environ["AI_API_KEY"] = "test_ai_key"
    os.environ["API_KEY"] = "test_api_key"
    
    yield
    
    # Restore original environment variables
    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]