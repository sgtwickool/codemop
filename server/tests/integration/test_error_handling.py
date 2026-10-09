"""
Integration tests for error handling scenarios.
"""
from unittest.mock import AsyncMock, patch

from tests.helpers import AUTH_HEADERS, SAMPLE_DIFF, FakeReviewModel, pr_event


class TestErrorHandlingIntegration:
    """Integration tests for error handling."""

    def test_database_connection_failure_webhook(self, post_webhook):
        """A database failure while storing the PR is a 500 that says so."""
        with patch('app.services.pr_service.pr_service.create_pr', side_effect=Exception("Database connection failed")):
            response = post_webhook(pr_event())

        assert response.status_code == 500
        assert "Database error" in response.json()["detail"]

    def test_network_failure_ai_api(self, post_webhook):
        """Analysis runs after the response, so an AI failure can't break the webhook."""
        failing_ai = AsyncMock(side_effect=Exception("AI API network timeout"))
        with patch('app.services.pr_analysis.fetch_pr_diff', new=AsyncMock(return_value=SAMPLE_DIFF)), \
             patch('app.services.pr_analysis.review_model', return_value=FakeReviewModel(failing_ai)):
            response = post_webhook(pr_event(number=456, title="Test PR with AI failure"))

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["analysis"] == "queued"
        failing_ai.assert_awaited_once()

    def test_network_failure_github_diff(self, post_webhook):
        """Analysis runs after the response, so a failed diff fetch can't break the webhook."""
        failing_fetch = AsyncMock(side_effect=Exception("GitHub API unavailable"))
        with patch('app.services.pr_analysis.fetch_pr_diff', new=failing_fetch):
            response = post_webhook(pr_event(number=789, title="Test PR with GitHub failure"))

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["analysis"] == "queued"
        failing_fetch.assert_awaited_once()

    def test_invalid_pr_data_missing_fields(self, post_webhook):
        """PR events without the data needed to store the PR are rejected, not a 500."""
        response = post_webhook({"action": "opened", "number": 999, "pull_request": {}, "repository": {}})

        assert response.status_code == 422
        assert "missing required fields" in response.json()["detail"]

    def test_invalid_suggestion_data(self, client, post_webhook):
        """A stored PR with no suggestions yet returns an empty list, not an error."""
        pr_id = post_webhook(pr_event(number=111)).json()["database_id"]

        response = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH_HEADERS)

        assert response.status_code == 200
        assert response.json()["suggestions_count"] == 0

    def test_malformed_json_webhook(self, post_webhook):
        response = post_webhook("{invalid json")

        assert response.status_code == 422
        assert "detail" in response.json()

    def test_malformed_json_suggestions(self, client):
        """A JSON content type on a GET doesn't matter: an unknown PR is a 404."""
        response = client.get(
            "/api/v1/pr/999/suggestions", headers={**AUTH_HEADERS, "Content-Type": "application/json"}
        )

        assert response.status_code == 404

    def test_internal_server_error_handling(self, client):
        """An unknown endpoint is a 404 with a detail message."""
        response = client.get("/api/v1/nonexistent")

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_error_response_format(self, client):
        """Error responses all have a string `detail`."""
        error_scenarios = [
            ("/api/v1/pr/999/suggestions", AUTH_HEADERS, 404),
            ("/api/v1/pr/999/suggestions", {}, 401),
            ("/api/v1/nonexistent", {}, 404),
        ]

        for endpoint, headers, expected_status in error_scenarios:
            response = client.get(endpoint, headers=headers)

            assert response.status_code == expected_status
            assert isinstance(response.json()["detail"], str)

    def test_error_recovery_after_failure(self, client, post_webhook):
        """A failed request doesn't affect the next one."""
        assert client.get("/api/v1/pr/999/suggestions").status_code == 401

        assert post_webhook(pr_event(number=333, title="Test PR after error")).status_code == 200
