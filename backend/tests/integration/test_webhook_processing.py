"""
Integration tests for how webhook events are processed: when analysis runs, how its
results replace earlier ones, PR state, and redeliveries.

The TestClient runs background tasks before returning, so the analysis has finished by
the time each request returns.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.db.session import session_scope
from app.models.pr import PR
from app.models.webhook_delivery import WebhookDelivery
from tests.helpers import AUTH_HEADERS, pr_event


def suggestion(description, line_number=10):
    return {
        "line_number": line_number,
        "file_path": "app.py",
        "description": description,
        "fix": "fixed()",
        "confidence": 0.9
    }


@pytest.fixture
def ai():
    """The AI analysis (and the diff fetch before it), mocked; set `return_value` or
    `side_effect` per test."""
    mock = AsyncMock(return_value=[])
    with patch("app.services.pr_analysis.fetch_pr_diff", new=AsyncMock(return_value="diff")), \
         patch("app.services.pr_analysis.analyze_diff", new=mock):
        yield mock


class TestWebhookProcessing:

    def test_new_commits_replace_earlier_suggestions(self, client, post_webhook, ai):
        ai.return_value = [suggestion("First issue"), suggestion("Second issue")]
        pr_id = post_webhook(pr_event("opened", sha="a" * 40)).json()["database_id"]

        ai.return_value = [suggestion("Issue in the new commit")]
        assert post_webhook(pr_event("synchronize", sha="b" * 40)).json()["analysis"] == "queued"

        data = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH_HEADERS).json()
        assert [s["description"] for s in data["suggestions"]] == ["Issue in the new commit"]
        assert data["analyzed_sha"] == "b" * 40

    def test_already_analysed_commit_is_not_analysed_again(self, post_webhook, ai):
        post_webhook(pr_event("opened", sha="a" * 40))

        response = post_webhook(pr_event("reopened", sha="a" * 40)).json()

        assert response["analysis"] == "skipped"
        assert "already been analysed" in response["reason"]
        ai.assert_awaited_once()

    @pytest.mark.parametrize("action", ["edited", "labeled", "assigned", "closed"])
    def test_events_that_dont_change_code_are_not_analysed(self, post_webhook, ai, action):
        response = post_webhook(pr_event(action)).json()

        assert response["status"] == "success"
        assert response["analysis"] == "skipped"
        ai.assert_not_awaited()

    def test_no_ai_key_means_no_analysis(self, post_webhook, ai, monkeypatch):
        """Without an AI key there's nothing to analyse with, and the commit isn't marked as analysed."""
        from app.config import settings
        monkeypatch.setattr(settings, "AI_API_KEY", "")

        response = post_webhook(pr_event("opened")).json()

        assert response["analysis"] == "skipped"
        assert response["reason"] == "AI_API_KEY is not configured"
        ai.assert_not_awaited()

    def test_drafts_are_analysed_once_ready_for_review(self, post_webhook, ai):
        draft = post_webhook(pr_event("opened", draft=True)).json()
        assert draft["analysis"] == "skipped"
        assert "draft" in draft["reason"]
        ai.assert_not_awaited()

        ready = post_webhook(pr_event("ready_for_review", draft=False)).json()
        assert ready["analysis"] == "queued"
        ai.assert_awaited_once()

    def test_failed_analysis_is_retried_on_redelivery(self, post_webhook, ai):
        ai.side_effect = [Exception("AI provider down"), [suggestion("Found on retry")]]
        post_webhook(pr_event("opened", sha="a" * 40), delivery_id="first-attempt")

        # A manual redelivery from GitHub gets a new delivery ID
        response = post_webhook(pr_event("opened", sha="a" * 40), delivery_id="manual-redelivery").json()

        assert response["analysis"] == "queued"
        assert ai.await_count == 2

    def test_results_for_a_superseded_commit_are_discarded(self, client, post_webhook, ai):
        """If new commits arrive while an analysis runs, its results are thrown away."""
        async def analysis_overtaken_by_a_push(diff):
            with session_scope() as db:
                db.query(PR).update({PR.head_sha: "c" * 40})
            return [suggestion("Stale")]

        ai.side_effect = analysis_overtaken_by_a_push
        pr_id = post_webhook(pr_event("opened", sha="a" * 40)).json()["database_id"]

        data = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH_HEADERS).json()
        assert data["suggestions"] == []
        assert data["analyzed_sha"] is None

    @pytest.mark.parametrize("state, merged, expected", [
        ("open", False, "open"),
        ("closed", False, "closed"),
        ("closed", True, "merged"),
    ])
    def test_pr_state_is_stored(self, client, post_webhook, ai, state, merged, expected):
        pr_id = post_webhook(pr_event("closed" if state == "closed" else "opened", state=state, merged=merged)).json()["database_id"]

        data = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH_HEADERS).json()
        assert data["status"] == expected


class TestWebhookRedeliveries:

    def test_redelivery_is_ignored(self, post_webhook, ai):
        first = post_webhook(pr_event("opened"), delivery_id="delivery-1")
        second = post_webhook(pr_event("opened"), delivery_id="delivery-1")

        assert first.json()["status"] == "success"
        assert second.status_code == 200
        assert second.json()["status"] == "duplicate"
        ai.assert_awaited_once()

    def test_delivery_that_failed_is_processed_when_redelivered(self, post_webhook, ai):
        with patch("app.services.pr_service.pr_service.create_pr", side_effect=Exception("Database down")):
            failed = post_webhook(pr_event("opened"), delivery_id="delivery-2")
        assert failed.status_code == 500

        retried = post_webhook(pr_event("opened"), delivery_id="delivery-2")

        assert retried.status_code == 200
        assert retried.json()["status"] == "success"

    def test_events_without_a_delivery_id_are_processed(self, post_webhook, ai):
        assert post_webhook(pr_event("opened")).json()["status"] == "success"
        assert post_webhook(pr_event("synchronize", sha="b" * 40)).json()["status"] == "success"

    def test_old_delivery_records_are_pruned(self, post_webhook, ai, db_session):
        """Delivery IDs are only kept for a week; GitHub can't redeliver older ones."""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db_session.add_all([
            WebhookDelivery(delivery_id="eight-days-old", event="pull_request", created_at=now - timedelta(days=8)),
            WebhookDelivery(delivery_id="six-days-old", event="pull_request", created_at=now - timedelta(days=6)),
        ])
        db_session.commit()

        post_webhook(pr_event("opened"), delivery_id="new-delivery")

        db_session.expire_all()
        remaining = sorted(d for (d,) in db_session.query(WebhookDelivery.delivery_id))
        assert remaining == ["new-delivery", "six-days-old"]
