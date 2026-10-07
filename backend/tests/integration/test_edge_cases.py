"""
Integration tests for edge cases and unusual scenarios.
"""
import pytest
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


class TestEdgeCasesIntegration:
    """Integration tests for edge cases."""

    def test_concurrent_webhook_requests(self, post_webhook, github_webhook_payload):
        """Concurrent deliveries for the same PR all succeed and store one PR."""
        with ThreadPoolExecutor(max_workers=5) as pool:
            responses = list(pool.map(lambda _: post_webhook(github_webhook_payload), range(5)))
        
        assert [response.status_code for response in responses] == [200] * 5
        assert len({response.json()["database_id"] for response in responses}) == 1

    def test_large_payload_handling(self, client):
        """Test handling of large payloads."""
        # Create a large payload
        large_payload = {
            "action": "opened",
            "number": 456,
            "pull_request": {
                "title": "Large PR" + "x" * 10000,  # Very long title
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/456",
                "diff_url": "https://github.com/testuser/testrepo/pull/456.diff",
                "body": "Large description" + "x" * 50000  # Very long description
            },
            "repository": {
                "name": "testrepo",
                "full_name": "testuser/testrepo"
            }
        }
        
        body = json.dumps(large_payload)
        from app.config import settings
        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        import hmac
        import hashlib
        signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        # Should handle large payload
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_malformed_json_various_types(self, client, github_signature):
        """Test handling of various types of malformed JSON."""
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
            response = client.post(
                "/api/v1/github/webhook",
                content=payload,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": github_signature(payload),
                    "Content-Type": "application/json"
                }
            )
            
            # Malformed JSON, and valid JSON that isn't an object, are both 422
            assert response.status_code == 422, payload

    def test_missing_required_fields(self, client, github_signature):
        """A pull_request event with an empty payload is rejected, not a 500."""
        response = client.post(
            "/api/v1/github/webhook",
            content="{}",
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": github_signature("{}"),
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 422
        assert "missing required fields" in response.json()["detail"]

    def test_unicode_handling(self, client):
        """Test handling of unicode characters."""
        payload = {
            "action": "opened",
            "number": 789,
            "pull_request": {
                "title": "Test PR with unicode: 你好世界 🌍",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/789",
                "diff_url": "https://github.com/testuser/testrepo/pull/789.diff",
                "body": "Unicode description: Привет мир 👋"
            },
            "repository": {
                "name": "testrepo",
                "full_name": "testuser/testrepo"
            }
        }
        
        body = json.dumps(payload)
        from app.config import settings
        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        import hmac
        import hashlib
        signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        # Should handle unicode
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_special_characters_in_urls(self, client):
        """Test handling of special characters in URLs."""
        payload = {
            "action": "opened",
            "number": 999,
            "pull_request": {
                "title": "Test PR",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/999?param=value&other=test",
                "diff_url": "https://github.com/testuser/testrepo/pull/999.diff?token=abc123"
            },
            "repository": {
                "name": "testrepo",
                "full_name": "testuser/testrepo"
            }
        }
        
        body = json.dumps(payload)
        from app.config import settings
        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        import hmac
        import hashlib
        signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        # Should handle special characters in URLs
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_very_long_request_paths(self, client):
        """Test handling of very long request paths."""
        # Test with a very long PR ID (should fail gracefully)
        very_long_id = "9" * 1000
        response = client.get(
            f"/api/v1/pr/{very_long_id}/suggestions",
            headers={
                "Authorization": "Bearer test_api_key"
            }
        )
        
        # Rejected as an out-of-range ID rather than overflowing the database query
        assert response.status_code == 422

    def test_empty_request_body(self, client, github_signature):
        """Test handling of empty request body."""
        response = client.post(
            "/api/v1/github/webhook",
            content="",
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": github_signature(""),
                "Content-Type": "application/json"
            }
        )
        
        # Should handle empty body
        assert response.status_code == 422  # Unprocessable Entity

    def test_invalid_content_type(self, client):
        """Test handling of invalid content types."""
        payload = {
            "action": "opened",
            "number": 111,
            "pull_request": {
                "title": "Test PR",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/111",
                "diff_url": "https://github.com/testuser/testrepo/pull/111.diff"
            },
            "repository": {
                "name": "testrepo",
                "full_name": "testuser/testrepo"
            }
        }
        
        body = json.dumps(payload)
        from app.config import settings
        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        import hmac
        import hashlib
        signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        
        # Test with wrong content type
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "text/plain"  # Wrong content type
            }
        )
        
        # 415 with a hint, since GitHub's default webhook content type is form-encoded
        assert response.status_code == 415
        assert "application/json" in response.json()["detail"]

    def test_nested_json_structures(self, client):
        """Test handling of deeply nested JSON structures."""
        # Create deeply nested payload
        nested_payload = {
            "action": "opened",
            "number": 222,
            "pull_request": {
                "title": "Test PR",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/222",
                "diff_url": "https://github.com/testuser/testrepo/pull/222.diff",
                "labels": [
                    {
                        "name": "bug",
                        "color": "red",
                        "description": "Bug fix",
                        "nested": {
                            "deep": {
                                "very_deep": {
                                    "extremely_deep": "value"
                                }
                            }
                        }
                    }
                ]
            },
            "repository": {
                "name": "testrepo",
                "full_name": "testuser/testrepo"
            }
        }
        
        body = json.dumps(nested_payload)
        from app.config import settings
        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        import hmac
        import hashlib
        signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        # Should handle nested structures
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_numeric_edge_cases(self, client):
        """Test handling of numeric edge cases."""
        # Test with very large PR number
        payload = {
            "action": "opened",
            "number": 9999999999,  # Very large PR number
            "pull_request": {
                "title": "Test PR",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/9999999999",
                "diff_url": "https://github.com/testuser/testrepo/pull/9999999999.diff"
            },
            "repository": {
                "name": "testrepo",
                "full_name": "testuser/testrepo"
            }
        }
        
        body = json.dumps(payload)
        from app.config import settings
        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        import hmac
        import hashlib
        signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        # Should handle large numbers
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_duplicate_webhook_events(self, client):
        """Test handling of duplicate webhook events."""
        payload = {
            "action": "opened",
            "number": 333,
            "pull_request": {
                "title": "Test PR",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/333",
                "diff_url": "https://github.com/testuser/testrepo/pull/333.diff"
            },
            "repository": {
                "name": "testrepo",
                "full_name": "testuser/testrepo"
            }
        }
        
        body = json.dumps(payload)
        from app.config import settings
        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        import hmac
        import hashlib
        signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        
        # Send the same webhook twice
        response1 = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        response2 = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        # Both should succeed (second should update existing PR)
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Should have same database ID (updated existing PR)
        assert data1["database_id"] == data2["database_id"]

    def test_case_sensitivity_in_paths(self, client):
        """Test case sensitivity in API paths."""
        # Test various case combinations
        paths = [
            "/api/v1/health",
            "/API/v1/health",
            "/Api/V1/Health",
            "/api/v1/HEALTH"
        ]
        
        for path in paths:
            response = client.get(path)
            # Should either work or return 404 consistently
            assert response.status_code in [200, 404]

    def test_header_case_sensitivity(self, client):
        """Test case sensitivity in headers."""
        payload = {
            "action": "opened",
            "number": 444,
            "pull_request": {
                "title": "Test PR",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/444",
                "diff_url": "https://github.com/testuser/testrepo/pull/444.diff"
            },
            "repository": {
                "name": "testrepo",
                "full_name": "testuser/testrepo"
            }
        }
        
        body = json.dumps(payload)
        from app.config import settings
        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        import hmac
        import hashlib
        signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        
        # Test with different header case variations
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "x-github-event": "pull_request",  # lowercase
                "x-hub-signature-256": signature,
                "content-type": "application/json"
            }
        )
        
        # Should work with lowercase headers
        assert response.status_code == 200