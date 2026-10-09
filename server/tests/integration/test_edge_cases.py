"""
Integration tests for edge cases and unusual scenarios.
"""
import json
from concurrent.futures import ThreadPoolExecutor

from tests.helpers import AUTH_HEADERS, pr_event, sign_body


class TestEdgeCasesIntegration:
    """Integration tests for edge cases."""

    def test_concurrent_webhook_requests(self, post_webhook, github_webhook_payload):
        """Concurrent deliveries for the same PR all succeed and store one PR."""
        with ThreadPoolExecutor(max_workers=5) as pool:
            responses = list(pool.map(lambda _: post_webhook(github_webhook_payload), range(5)))

        assert [response.status_code for response in responses] == [200] * 5
        assert len({response.json()["database_id"] for response in responses}) == 1

    def test_large_payload_handling(self, post_webhook):
        """A very long title and description are stored without error."""
        payload = pr_event(number=456, title="Large PR" + "x" * 10000)
        payload["pull_request"]["body"] = "Large description" + "x" * 50000

        response = post_webhook(payload)

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_malformed_json_various_types(self, post_webhook):
        """Malformed JSON, and valid JSON that isn't an object, are both 422."""
        malformed_payloads = [
            "{invalid json",
            "['not', 'an', 'object']",
            "{'single_quotes': 'invalid'}",
            "true",
            "false",
            "null",
            "123",
            '"just a string"',
            "",
            "   "
        ]

        for payload in malformed_payloads:
            assert post_webhook(payload).status_code == 422, payload

    def test_missing_required_fields(self, post_webhook):
        """A pull_request event with an empty payload is rejected, not a 500."""
        response = post_webhook("{}")

        assert response.status_code == 422
        assert "missing required fields" in response.json()["detail"]

    def test_unicode_handling(self, post_webhook):
        """Unicode in the title and description is stored without error."""
        payload = pr_event(number=789, title="Test PR with unicode: 你好世界 🌍")
        payload["pull_request"]["body"] = "Unicode description: Привет мир 👋"

        response = post_webhook(payload)

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_special_characters_in_urls(self, post_webhook):
        """Query strings in the PR's URLs are stored without error."""
        payload = pr_event(number=999)
        payload["pull_request"]["html_url"] = "https://github.com/testuser/testrepo/pull/999?param=value&other=test"
        payload["pull_request"]["diff_url"] = "https://github.com/testuser/testrepo/pull/999.diff?token=abc123"

        response = post_webhook(payload)

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_very_long_request_paths(self, client):
        """A huge PR ID is rejected as out of range rather than overflowing the database query."""
        response = client.get(f"/api/v1/pr/{'9' * 1000}/suggestions", headers=AUTH_HEADERS)

        assert response.status_code == 422

    def test_empty_request_body(self, post_webhook):
        assert post_webhook("").status_code == 422

    def test_invalid_content_type(self, post_webhook):
        """415 with a hint, since GitHub's default webhook content type is form-encoded."""
        response = post_webhook(pr_event(number=111), content_type="text/plain")

        assert response.status_code == 415
        assert "application/json" in response.json()["detail"]

    def test_nested_json_structures(self, post_webhook):
        """Deeply nested fields the app doesn't use are ignored."""
        payload = pr_event(number=222)
        payload["pull_request"]["labels"] = [
            {"name": "bug", "color": "red", "nested": {"deep": {"very_deep": {"extremely_deep": "value"}}}}
        ]

        response = post_webhook(payload)

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_numeric_edge_cases(self, post_webhook):
        """PR numbers beyond 32 bits are stored (they're 64-bit in the database)."""
        response = post_webhook(pr_event(number=9999999999))

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_duplicate_webhook_events(self, post_webhook):
        """The same event sent twice (without a delivery ID) updates the one stored PR."""
        payload = pr_event(number=333)

        response1 = post_webhook(payload)
        response2 = post_webhook(payload)

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["database_id"] == response2.json()["database_id"]

    def test_case_sensitivity_in_paths(self, client):
        """Paths are matched exactly: only the lowercase one exists."""
        assert client.get("/api/v1/health").status_code == 200
        for path in ["/API/v1/health", "/Api/V1/Health", "/api/v1/HEALTH"]:
            assert client.get(path).status_code == 404, path

    def test_header_case_sensitivity(self, client):
        """HTTP header names are case-insensitive, so lowercase GitHub headers work."""
        body = json.dumps(pr_event(number=444))

        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "x-github-event": "pull_request",
                "x-hub-signature-256": sign_body(body),
                "content-type": "application/json"
            }
        )

        assert response.status_code == 200
