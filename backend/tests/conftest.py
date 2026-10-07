"""
Pytest configuration and fixtures for CodeMop backend tests.

Settings are fixed here, before the app is imported, so the tests never depend on a
developer's .env file and never reach a real database, GitHub or AI provider.
"""
import hashlib
import hmac
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

TEST_WEBHOOK_SECRET = "test_secret"
TEST_API_KEY = "test_api_key"

_test_db_dir = tempfile.mkdtemp(prefix="codemop-tests-")

# Environment variables take precedence over the .env file
os.environ.update({
    "APP_ENV": "test",
    "DEBUG": "false",
    # TEST_DATABASE_URL lets CI point the suite at a real Postgres
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_test_db_dir}/test.db"),
    "GITHUB_WEBHOOK_SECRET": TEST_WEBHOOK_SECRET,
    "API_KEY": TEST_API_KEY,
    "AI_API_KEY": "test_ai_key",
    "AI_API_URL": "https://ai.invalid/v1/chat/completions",
    "ENABLE_METRICS": "false",
    "SENTRY_DSN": "",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.db.session import engine, SessionLocal, init_db  # noqa: E402
from app.models.base import Base  # noqa: E402


def drop_everything():
    """Drop the app's tables and the migration history."""
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")


@pytest.fixture(scope="session", autouse=True)
def database():
    """Build the schema once per test session, through the migrations the app uses."""
    drop_everything()
    init_db()
    yield
    drop_everything()
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    """Empty every table after each test so tests can't affect each other."""
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture(autouse=True)
def rate_limiting_disabled():
    """Rate limits are off by default; tests that exercise them use `rate_limiting`."""
    limiter.enabled = False
    limiter.reset()
    yield
    limiter.enabled = False


@pytest.fixture
def rate_limiting():
    """Turn rate limiting on, starting from empty counters."""
    limiter.reset()
    limiter.enabled = True
    yield limiter


@pytest.fixture(autouse=True)
def no_network():
    """Fail outbound HTTP calls by default; tests that need a response mock them."""
    blocked = AsyncMock(side_effect=RuntimeError("Network access is disabled in tests"))
    with patch("app.services.ai_analysis.fetch_with_retry", new=blocked):
        yield blocked


@pytest.fixture
def db_session():
    """A database session for tests that use the service layer directly."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def client():
    """A test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
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


def sign_body(body) -> str:
    """GitHub's X-Hub-Signature-256 value for a raw request body."""
    if isinstance(body, str):
        body = body.encode()
    return "sha256=" + hmac.new(TEST_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def github_signature():
    """Sign a dict payload as it will be sent (json.dumps), or a raw str/bytes body."""
    def generate_signature(payload):
        if isinstance(payload, (str, bytes)):
            return sign_body(payload)
        return sign_body(json.dumps(payload))

    return generate_signature
