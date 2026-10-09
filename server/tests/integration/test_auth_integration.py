"""
Integration tests for API authentication.
"""
import json


from tests.helpers import AUTH_HEADERS, pr_event


class TestAuthenticationIntegration:
    """Integration tests for API authentication."""

    def test_api_key_authentication_success(self, client, post_webhook):
        """A valid API key reads a stored PR's suggestions."""
        pr_id = post_webhook(pr_event(title="Test PR for auth")).json()["database_id"]
        
        response = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH_HEADERS)
        
        assert response.status_code == 200
        assert response.json()["pr_id"] == pr_id

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
        """The health check needs no authentication."""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200

    def test_webhook_uses_signatures_not_api_keys(self, client, github_signature):
        """The webhook authenticates GitHub by signature; it doesn't need the API key."""
        payload = {"action": "test"}
        
        unsigned = client.post("/api/v1/github/webhook", json=payload)
        signed = client.post(
            "/api/v1/github/webhook",
            content=json.dumps(payload),
            headers={"X-Hub-Signature-256": github_signature(payload), "Content-Type": "application/json"}
        )
        
        assert unsigned.status_code == 401
        assert signed.status_code == 200

    def test_unset_api_key_rejects_every_request(self, client, monkeypatch):
        """With no API_KEY configured, no token (not even an empty one) is accepted."""
        from app.config import settings
        monkeypatch.setattr(settings, "API_KEY", "")
        
        for header in ["Bearer ", "Bearer", "", " "]:
            response = client.get("/api/v1/pr/1/suggestions", headers={"Authorization": header})
            assert response.status_code == 401, repr(header)
