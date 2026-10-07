"""
Integration tests for how webhook events are processed: when analysis runs, how its
results replace earlier ones, PR state, and redeliveries.

The TestClient runs background tasks before returning, so the analysis has finished by
the time each request returns.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.db.session import SessionLocal
from app.models.pr import PR

AUTH = {"Authorization": "Bearer test_api_key"}


def pr_event(action="opened", sha="a" * 40, state="open", merged=False, draft=False, number=42):
    return {
        "action": action,
        "number": number,
        "pull_request": {
            "title": "Add a feature",
            "user": {"login": "testuser"},
            "head": {"ref": "feature", "sha": sha},
            "state": state,
            "merged": merged,
            "draft": draft,
            "html_url": f"https://github.com/testuser/testrepo/pull/{number}",
            "diff_url": f"https://github.com/testuser/testrepo/pull/{number}.diff"
        },
        "repository": {"name": "testrepo", "full_name": "testuser/testrepo"}
    }


def suggestion(description, line_number=10):
    return {
        "line_number": line_number,
        "file_path": "app.py",
        "description": description,
        "fix": "fixed()",
        "confidence": 0.9
    }


@pytest.fixture
def send(client, github_signature):
    """POST a pull_request event, optionally with an X-GitHub-Delivery ID."""
    def _send(payload, delivery_id=None):
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": github_signature(payload),
            "Content-Type": "application/json"
        }
        if delivery_id:
            headers["X-GitHub-Delivery"] = delivery_id
        return client.post("/api/v1/github/webhook", content=json.dumps(payload), headers=headers)
    return _send


@pytest.fixture
def ai():
    """The AI analysis, mocked; set `return_value` or `side_effect` per test."""
    mock = AsyncMock(return_value=[])
    with patch("app.services.pr_analysis.analyze_pr_with_ai", new=mock):
        yield mock


class TestWebhookProcessing:

    def test_new_commits_replace_earlier_suggestions(self, client, send, ai):
        ai.return_value = [suggestion("First issue"), suggestion("Second issue")]
        pr_id = send(pr_event("opened", sha="a" * 40)).json()["database_id"]

        ai.return_value = [suggestion("Issue in the new commit")]
        assert send(pr_event("synchronize", sha="b" * 40)).json()["analysis"] == "queued"

        data = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH).json()
        assert [s["description"] for s in data["suggestions"]] == ["Issue in the new commit"]
        assert data["suggestions"][0]["head_sha"] == "b" * 40
        assert data["analyzed_sha"] == "b" * 40

    def test_already_analysed_commit_is_not_analysed_again(self, send, ai):
        send(pr_event("opened", sha="a" * 40))

        response = send(pr_event("reopened", sha="a" * 40)).json()

        assert response["analysis"] == "skipped"
        assert "already been analysed" in response["reason"]
        ai.assert_awaited_once()

    @pytest.mark.parametrize("action", ["edited", "labeled", "assigned", "closed"])
    def test_events_that_dont_change_code_are_not_analysed(self, send, ai, action):
        response = send(pr_event(action)).json()

        assert response["status"] == "success"
        assert response["analysis"] == "skipped"
        ai.assert_not_awaited()

    def test_drafts_are_analysed_once_ready_for_review(self, send, ai):
        draft = send(pr_event("opened", draft=True)).json()
        assert draft["analysis"] == "skipped"
        assert "draft" in draft["reason"]
        ai.assert_not_awaited()

        ready = send(pr_event("ready_for_review", draft=False)).json()
        assert ready["analysis"] == "queued"
        ai.assert_awaited_once()

    def test_failed_analysis_is_retried_on_redelivery(self, send, ai):
        ai.side_effect = [Exception("AI provider down"), [suggestion("Found on retry")]]
        send(pr_event("opened", sha="a" * 40), delivery_id="first-attempt")

        # A manual redelivery from GitHub gets a new delivery ID
        response = send(pr_event("opened", sha="a" * 40), delivery_id="manual-redelivery").json()

        assert response["analysis"] == "queued"
        assert ai.await_count == 2

    def test_results_for_a_superseded_commit_are_discarded(self, client, send, ai):
        """If new commits arrive while an analysis runs, its results are thrown away."""
        async def analysis_overtaken_by_a_push(diff_url):
            db = SessionLocal()
            db.query(PR).update({PR.head_sha: "c" * 40})
            db.commit()
            db.close()
            return [suggestion("Stale")]

        ai.side_effect = analysis_overtaken_by_a_push
        pr_id = send(pr_event("opened", sha="a" * 40)).json()["database_id"]

        data = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH).json()
        assert data["suggestions"] == []
        assert data["analyzed_sha"] is None

    def test_incomplete_suggestions_are_skipped(self, client, send, ai):
        ai.return_value = [suggestion("Complete"), {"line_number": 3, "file_path": "app.py"}]
        pr_id = send(pr_event("opened")).json()["database_id"]

        data = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH).json()
        assert [s["description"] for s in data["suggestions"]] == ["Complete"]

    @pytest.mark.parametrize("state, merged, expected", [
        ("open", False, "open"),
        ("closed", False, "closed"),
        ("closed", True, "merged"),
    ])
    def test_pr_state_is_stored(self, client, send, ai, state, merged, expected):
        pr_id = send(pr_event("closed" if state == "closed" else "opened", state=state, merged=merged)).json()["database_id"]

        data = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH).json()
        assert data["status"] == expected


class TestWebhookRedeliveries:

    def test_redelivery_is_ignored(self, send, ai):
        first = send(pr_event("opened"), delivery_id="delivery-1")
        second = send(pr_event("opened"), delivery_id="delivery-1")

        assert first.json()["status"] == "success"
        assert second.status_code == 200
        assert second.json()["status"] == "duplicate"
        ai.assert_awaited_once()

    def test_delivery_that_failed_is_processed_when_redelivered(self, send, ai):
        with patch("app.services.pr_service.pr_service.create_pr", side_effect=Exception("Database down")):
            failed = send(pr_event("opened"), delivery_id="delivery-2")
        assert failed.status_code == 500

        retried = send(pr_event("opened"), delivery_id="delivery-2")

        assert retried.status_code == 200
        assert retried.json()["status"] == "success"

    def test_events_without_a_delivery_id_are_processed(self, send, ai):
        assert send(pr_event("opened")).json()["status"] == "success"
        assert send(pr_event("synchronize", sha="b" * 40)).json()["status"] == "success"
