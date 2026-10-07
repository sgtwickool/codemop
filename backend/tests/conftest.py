"""
Pytest configuration and fixtures for CodeMop backend tests.

Settings are fixed here, before the app is imported, so the tests never depend on a
developer's .env file and never reach a real database, GitHub or AI provider.
"""
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from tests.helpers import TEST_API_KEY, TEST_WEBHOOK_SECRET, pr_event, sign_body

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
from app.db.session import engine, init_db, session_scope  # noqa: E402
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
    # Every outbound call goes through app.utils.http.fetch_with_retry
    with patch("app.utils.http.fetch_with_retry", new=blocked):
        yield blocked


@pytest.fixture
def db_session():
    """A database session for tests that use the service layer directly."""
    with session_scope() as session:
        yield session


@pytest.fixture
def client():
    """A test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def github_webhook_payload():
    """Standard GitHub webhook payload for testing."""
    return pr_event()


@pytest.fixture
def github_signature():
    """Sign a dict payload as it will be sent (json.dumps), or a raw str/bytes body."""
    def generate_signature(payload):
        if isinstance(payload, (str, bytes)):
            return sign_body(payload)
        return sign_body(json.dumps(payload))

    return generate_signature


@pytest.fixture
def post_webhook(client):
    """POST a signed webhook (a dict payload, or a raw str body) to the app."""
    def _post(payload, event="pull_request", delivery_id=None):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        headers = {
            "X-GitHub-Event": event,
            "X-Hub-Signature-256": sign_body(body),
            "Content-Type": "application/json"
        }
        if delivery_id:
            headers["X-GitHub-Delivery"] = delivery_id
        return client.post("/api/v1/github/webhook", content=body, headers=headers)
    return _post

