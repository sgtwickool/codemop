"""
Integration tests for GitHub webhook endpoint.
"""
import json

import pytest

from tests.helpers import pr_event


class TestWebhookIntegration:
    """Integration tests for GitHub webhook endpoint."""
    
    def test_health_check_endpoint(self, client):
        """Test the health check endpoint."""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
    
    def test_webhook_without_signature(self, client):
        """Test webhook without signature (should fail)."""
        response = client.post(
            "/api/v1/github/webhook",
            content=json.dumps(pr_event()),
            headers={
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    def test_webhook_with_valid_signature(self, post_webhook, github_webhook_payload):
        response = post_webhook(github_webhook_payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["pr_number"] == 123
        assert data["action"] == "opened"
        assert data["repository"] == "testuser/testrepo"
        assert "database_id" in data
        assert "timestamp" in data
    
    def test_webhook_non_pr_event(self, post_webhook):
        """Signed events other than pull_request are acknowledged and ignored."""
        response = post_webhook({"ref": "refs/heads/main"}, event="push")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "not a pull_request event"
    
    def test_webhook_invalid_signature(self, client, github_webhook_payload):
        """Test webhook with invalid signature."""
        body = json.dumps(github_webhook_payload)
        
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "invalid_signature",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    def test_webhook_pr_update(self, post_webhook):
        """A later event for the same PR updates the stored PR."""
        database_id = post_webhook(pr_event("opened")).json()["database_id"]
        
        response = post_webhook(pr_event("closed", title="Updated Test PR", state="closed"))
        
        assert response.status_code == 200
        assert response.json()["action"] == "closed"
        assert response.json()["database_id"] == database_id
    
    def test_unsigned_non_pr_event_is_rejected(self, client):
        """Every event needs a valid signature, not just pull_request ones."""
        response = client.post(
            "/api/v1/github/webhook",
            content=json.dumps({"ref": "refs/heads/main"}),
            headers={"X-GitHub-Event": "push", "Content-Type": "application/json"}
        )
        
        assert response.status_code == 401
    
    def test_ping_event(self, post_webhook):
        """GitHub's ping (sent when the webhook is created) gets a clear reply."""
        response = post_webhook({"zen": "Keep it logically awesome.", "hook_id": 1}, event="ping")
        
        assert response.status_code == 200
        assert response.json()["status"] == "pong"
    
    @pytest.mark.parametrize("app_env, expected_status", [
        ("production", 503),  # a missing secret must never mean "skip the check" in a deployment
        ("development", 200),
    ])
    def test_unset_webhook_secret(self, post_webhook, monkeypatch, github_webhook_payload, app_env, expected_status):
        from app.config import settings
        monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "")
        monkeypatch.setattr(settings, "APP_ENV", app_env)
        
        assert post_webhook(github_webhook_payload).status_code == expected_status
