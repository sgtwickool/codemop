"""
The database is used synchronously, so it must never be used on the event loop: a slow query
there would stall every other request, and the background reviews, until it finished.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.db.pr_repository import pr_repository
from app.services.pr_service import pr_service
from app.services.suggestion_service import suggestion_service
from tests.helpers import AUTH_HEADERS, SAMPLE_DIFF, FakeReviewModel, pr_event, suggestion


def off_the_event_loop(function, calls):
    """Wraps `function` to record, for each call, whether it ran with no event loop in its thread"""
    def wrapper(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            calls.append(False)
        except RuntimeError:
            calls.append(True)
        return function(*args, **kwargs)
    return wrapper


@pytest.fixture
def ai():
    model = FakeReviewModel(AsyncMock(return_value=[suggestion("An issue")]))
    with patch("app.services.pr_analysis.fetch_pr_diff", new=AsyncMock(return_value=SAMPLE_DIFF)), \
         patch("app.services.pr_analysis.review_model", return_value=model):
        yield


def test_the_webhook_stores_the_pr_off_the_event_loop(post_webhook, ai):
    calls = []
    with patch.object(pr_service, "create_pr", off_the_event_loop(pr_service.create_pr, calls)):
        assert post_webhook(pr_event("opened"), delivery_id="d-1").json()["status"] == "success"

    assert calls == [True]


def test_the_background_review_stores_its_results_off_the_event_loop(post_webhook, ai):
    calls = []
    with patch.object(pr_repository, "get", off_the_event_loop(pr_repository.get, calls)):
        assert post_webhook(pr_event("opened")).json()["analysis"] == "queued"

    assert calls == [True]


def test_reading_suggestions_happens_off_the_event_loop(client, post_webhook, ai):
    pr_id = post_webhook(pr_event("opened")).json()["database_id"]
    calls = []
    getter = off_the_event_loop(suggestion_service.get_suggestions_by_pr_id, calls)
    with patch.object(suggestion_service, "get_suggestions_by_pr_id", getter):
        assert client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH_HEADERS).status_code == 200
        assert client.get("/api/v1/repos/testuser/testrepo/pulls/123/suggestions", headers=AUTH_HEADERS).status_code == 200

    assert calls == [True, True]
