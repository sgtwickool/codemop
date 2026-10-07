"""
Integration tests for rate limiting functionality.

Rate limiting is disabled for the rest of the suite; these tests opt in with the
`rate_limiting` fixture, which also starts every test with empty counters.
"""
import json

from app.core.security_config import RATE_LIMITS

AUTH = {"Authorization": "Bearer test_api_key"}


def _limit(endpoint: str) -> int:
    """Requests allowed per window, e.g. "10/minute" -> 10."""
    return int(RATE_LIMITS[endpoint].split("/")[0])


def _post_webhook(client, payload, github_signature):
    return client.post(
        "/api/v1/github/webhook",
        content=json.dumps(payload),
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": github_signature(payload),
            "Content-Type": "application/json"
        }
    )


class TestRateLimitingIntegration:
    """Integration tests for rate limiting."""

    def test_webhook_rate_limiting(self, client, rate_limiting, github_webhook_payload, github_signature):
        """Requests beyond the webhook limit get 429."""
        statuses = [
            _post_webhook(client, github_webhook_payload, github_signature).status_code
            for _ in range(_limit("webhook") + 1)
        ]

        assert statuses[:-1] == [200] * _limit("webhook")
        assert statuses[-1] == 429

    def test_suggestions_rate_limiting(self, client, rate_limiting, github_webhook_payload, github_signature):
        """Requests beyond the suggestions limit get 429."""
        pr_id = _post_webhook(client, github_webhook_payload, github_signature).json()["database_id"]

        statuses = [
            client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH).status_code
            for _ in range(_limit("suggestions") + 1)
        ]

        assert statuses[:-1] == [200] * _limit("suggestions")
        assert statuses[-1] == 429

    def test_rate_limit_exceeded_response(self, client, rate_limiting):
        """A 429 uses the standard error shape and says when to retry."""
        for _ in range(_limit("suggestions") + 1):
            response = client.get("/api/v1/pr/1/suggestions", headers=AUTH)

        assert response.status_code == 429
        data = response.json()
        assert "Rate limit exceeded" in data["detail"]
        assert int(response.headers["Retry-After"]) > 0

    def test_rate_limiting_different_endpoints(self, client, rate_limiting, github_webhook_payload, github_signature):
        """Exhausting the webhook limit doesn't block the suggestions endpoint."""
        responses = [
            _post_webhook(client, github_webhook_payload, github_signature)
            for _ in range(_limit("webhook") + 1)
        ]
        assert responses[-1].status_code == 429

        pr_id = responses[0].json()["database_id"]
        response = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH)
        assert response.status_code == 200
