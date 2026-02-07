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

# Test database configuration
TEST_DATABASE_URL = "sqlite:///:memory:"

# Create test engine and session
test_engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

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
    """Create a test client for the FastAPI app."""
    # Use test database
    import app.db.session
    from app.main import app as fastapi_app
    
    original_get_db = app.db.session.get_db
    original_init_db = app.db.session.init_db
    
    def test_init_db():
        """Test database initialization."""
        Base.metadata.create_all(bind=test_engine)
    
    def test_get_db():
        """Test database session dependency."""
        session = TestSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    # Override database functions
    app.db.session.get_db = test_get_db
    app.db.session.init_db = test_init_db
    
    # Create test client
    test_client = TestClient(fastapi_app)
    
    yield test_client
    
    # Restore original functions
    app.db.session.get_db = original_get_db
    app.db.session.init_db = original_init_db

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
    """Generate a valid GitHub webhook signature."""
    import hmac
    import hashlib
    import json
    
    def generate_signature(payload, secret="test_secret"):
        body = json.dumps(payload)
        return "sha256=" + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    
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