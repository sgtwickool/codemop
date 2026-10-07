"""
Integration tests for API authentication.
"""
import pytest
import json


class TestAuthenticationIntegration:
    """Integration tests for API authentication."""

    def test_api_key_authentication_success(self, client):
        """Test successful authentication with valid API key."""
        # First create a PR via webhook
        payload = {
            "action": "opened",
            "number": 123,
            "pull_request": {
                "title": "Test PR for auth",
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
        
        # Create the PR
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        pr_data = response.json()
        pr_id = pr_data["database_id"]
        
        # Test suggestions endpoint with valid API key
        response = client.get(
            f"/api/v1/pr/{pr_id}/suggestions",
            headers={
                "Authorization": "Bearer test_api_key"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["pr_id"] == pr_id

    def test_api_key_authentication_missing(self, client):
        """Test authentication failure when API key is missing."""
        # Test suggestions endpoint without API key
        response = client.get("/api/v1/pr/999/suggestions")
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "Authorization header missing" in data["detail"]

    def test_api_key_authentication_invalid(self, client):
        """Test authentication failure with invalid API key."""
        # Test suggestions endpoint with invalid API key
        response = client.get(
            "/api/v1/pr/999/suggestions",
            headers={
                "Authorization": "Bearer invalid_api_key_12345"
            }
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "Invalid API key" in data["detail"]

    def test_api_key_authentication_wrong_format(self, client):
        """Test authentication failure with wrong authorization format."""
        # Test suggestions endpoint with wrong auth format
        response = client.get(
            "/api/v1/pr/999/suggestions",
            headers={
                "Authorization": "Basic invalid_format"
            }
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_api_key_authentication_empty_token(self, client):
        """Test authentication failure with empty bearer token."""
        # Test suggestions endpoint with empty token
        response = client.get(
            "/api/v1/pr/999/suggestions",
            headers={
                "Authorization": "Bearer "
            }
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_api_key_authentication_malformed_header(self, client):
        """Test authentication failure with malformed authorization header."""
        # Test suggestions endpoint with malformed header
        response = client.get(
            "/api/v1/pr/999/suggestions",
            headers={
                "Authorization": "Bearer"
            }
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_authentication_required_endpoints(self, client):
        """Test that all protected endpoints require authentication."""
        protected_endpoints = [
            "/api/v1/pr/1/suggestions"
        ]
        
        for endpoint in protected_endpoints:
            response = client.get(endpoint)
            assert response.status_code == 401
            data = response.json()
            assert "detail" in data

    def test_authentication_not_required_endpoints(self, client):
        """Test that public endpoints don't require authentication."""
        public_endpoints = [
            "/api/v1/health",
            "/api/v1/github/webhook"
        ]
        
        for endpoint in public_endpoints:
            if endpoint == "/api/v1/github/webhook":
                # Webhook requires POST
                response = client.post(endpoint, json={"action": "test"})
            else:
                response = client.get(endpoint)
            
            # Should not be 401 (Unauthorized)
            assert response.status_code != 401