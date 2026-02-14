"""
Integration tests for rate limiting functionality.
"""
import pytest
import json
import time


class TestRateLimitingIntegration:
    """Integration tests for rate limiting."""

    def test_webhook_rate_limiting(self, client):
        """Test rate limiting on webhook endpoint."""
        # Create a valid webhook payload
        payload = {
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
        
        body = json.dumps(payload)
        from app.config import settings
        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        import hmac
        import hashlib
        signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        
        # Make multiple requests to test rate limiting
        successful_requests = 0
        rate_limited_requests = 0
        
        for i in range(20):  # Try more requests than the limit
            response = client.post(
                "/api/v1/github/webhook",
                data=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": signature,
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                successful_requests += 1
            elif response.status_code == 429:
                rate_limited_requests += 1
                break  # Stop if we hit rate limit
            else:
                break  # Stop on other errors
        
        # Should have some successful requests and eventually hit rate limit
        assert successful_requests > 0
        assert rate_limited_requests > 0

    def test_suggestions_rate_limiting(self, client):
        """Test rate limiting on suggestions endpoint."""
        # First create a PR via webhook
        payload = {
            "action": "opened",
            "number": 456,
            "pull_request": {
                "title": "Test PR for rate limiting",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/456",
                "diff_url": "https://github.com/testuser/testrepo/pull/456.diff"
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
        
        # Create the PR
        response = client.post(
            "/api/v1/github/webhook",
            data=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        pr_data = response.json()
        pr_id = pr_data["database_id"]
        
        # Test suggestions endpoint rate limiting
        successful_requests = 0
        rate_limited_requests = 0
        
        for i in range(20):  # Try more requests than the limit
            response = client.get(
                f"/api/v1/pr/{pr_id}/suggestions",
                headers={
                    "Authorization": "Bearer test_api_key"
                }
            )
            
            if response.status_code == 200:
                successful_requests += 1
            elif response.status_code == 429:
                rate_limited_requests += 1
                break  # Stop if we hit rate limit
            else:
                break  # Stop on other errors
        
        # Should have some successful requests and eventually hit rate limit
        assert successful_requests > 0
        assert rate_limited_requests > 0

    def test_rate_limit_exceeded_response(self, client):
        """Test proper response format when rate limit is exceeded."""
        # First create a PR via webhook
        payload = {
            "action": "opened",
            "number": 789,
            "pull_request": {
                "title": "Test PR for rate limit response",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/789",
                "diff_url": "https://github.com/testuser/testrepo/pull/789.diff"
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
        
        # Create the PR
        response = client.post(
            "/api/v1/github/webhook",
            data=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        pr_data = response.json()
        pr_id = pr_data["database_id"]
        
        # Make multiple requests to trigger rate limit
        for i in range(10):
            response = client.get(
                f"/api/v1/pr/{pr_id}/suggestions",
                headers={
                    "Authorization": "Bearer test_api_key"
                }
            )
            
            if response.status_code == 429:
                # Check rate limit exceeded response structure
                data = response.json()
                assert "detail" in data
                assert "Rate limit exceeded" in data["detail"]
                assert "Retry-After" in response.headers
                break

    def test_rate_limiting_different_endpoints(self, client):
        """Test that different endpoints have different rate limits."""
        # Create test PRs for both endpoints
        pr1_payload = {
            "action": "opened",
            "number": 111,
            "pull_request": {
                "title": "Test PR 1",
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
        
        pr2_payload = {
            "action": "opened",
            "number": 222,
            "pull_request": {
                "title": "Test PR 2",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/222",
                "diff_url": "https://github.com/testuser/testrepo/pull/222.diff"
            },
            "repository": {
                "name": "testrepo",
                "full_name": "testuser/testrepo"
            }
        }
        
        # Create PRs
        for payload in [pr1_payload, pr2_payload]:
            body = json.dumps(payload)
            from app.config import settings
            secret = settings.GITHUB_WEBHOOK_SECRET.encode()
            import hmac
            import hashlib
            signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
            
            response = client.post(
                "/api/v1/github/webhook",
                data=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": signature,
                    "Content-Type": "application/json"
                }
            )
            assert response.status_code == 200
        
        # Test rate limiting on both endpoints
        webhook_limits = []
        suggestions_limits = []
        
        # Test webhook rate limiting
        for i in range(15):
            response = client.post(
                "/api/v1/github/webhook",
                data=json.dumps(pr1_payload),
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": "sha256=" + hmac.new(secret, json.dumps(pr1_payload).encode(), hashlib.sha256).hexdigest(),
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 429:
                webhook_limits.append(i)
                break
        
        # Test suggestions rate limiting
        for i in range(15):
            response = client.get(
                f"/api/v1/pr/{pr1_payload['pull_request']['number']}/suggestions",
                headers={
                    "Authorization": "Bearer test_api_key"
                }
            )
            
            if response.status_code == 429:
                suggestions_limits.append(i)
                break
        
        # Both endpoints should have rate limits, but they might be different
        assert len(webhook_limits) > 0 or len(suggestions_limits) > 0