"""
Integration tests for rate limiting functionality.

Rate limiting is disabled for the rest of the suite; these tests opt in with the
`rate_limiting` fixture, which also starts every test with empty counters.
"""
from app.core.security_config import RATE_LIMITS
from tests.helpers import AUTH_HEADERS, pr_event


def _limit(endpoint: str) -> int:
    """Requests allowed per window, e.g. "60/minute" -> 60."""
    return int(RATE_LIMITS[endpoint].split("/")[0])


class TestRateLimitingIntegration:
    """Integration tests for rate limiting."""

    def test_webhook_is_not_rate_limited(self, rate_limiting, post_webhook, monkeypatch):
        """GitHub's deliveries share a few IPs, so a limit would only drop real events."""
        from app.config import settings
        monkeypatch.setattr(settings, "AI_API_KEY", "")  # no analysis: only the webhook is under test

        # More than the old limit of 10 a minute
        statuses = {post_webhook(pr_event()).status_code for _ in range(20)}

        assert statuses == {200}

    def test_health_check_is_not_rate_limited(self, client, rate_limiting):
        statuses = {client.get("/api/v1/health").status_code for _ in range(_limit("suggestions") + 1)}

        assert statuses == {200}

    def test_suggestions_rate_limiting(self, client, rate_limiting, post_webhook):
        """Requests beyond the suggestions limit get 429."""
        pr_id = post_webhook(pr_event()).json()["database_id"]

        statuses = [
            client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH_HEADERS).status_code
            for _ in range(_limit("suggestions") + 1)
        ]

        assert statuses[:-1] == [200] * _limit("suggestions")
        assert statuses[-1] == 429

    def test_rate_limit_exceeded_response(self, client, rate_limiting):
        """A 429 uses the standard error shape and says when to retry."""
        for _ in range(_limit("suggestions") + 1):
            response = client.get("/api/v1/pr/1/suggestions", headers=AUTH_HEADERS)

        assert response.status_code == 429
        data = response.json()
        assert "Rate limit exceeded" in data["detail"]
        assert int(response.headers["Retry-After"]) > 0

    def test_exhausted_api_limit_doesnt_block_webhooks(self, client, rate_limiting, post_webhook):
        for _ in range(_limit("suggestions") + 1):
            client.get("/api/v1/pr/1/suggestions", headers=AUTH_HEADERS)

        response = post_webhook(pr_event())

        assert response.status_code == 200
