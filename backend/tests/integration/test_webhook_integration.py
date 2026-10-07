"""
Integration tests for GitHub webhook endpoint.
"""
import pytest
import json


class TestWebhookIntegration:
    """Integration tests for GitHub webhook endpoint."""
    
    def test_health_check_endpoint(self, client):
        """Test the health check endpoint."""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
    
    def test_webhook_without_signature(self, client):
        """Test webhook without signature (should fail)."""
        payload = {
            "action": "opened",
            "number": 123,
            "pull_request": {
                "title": "Test PR",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"}
            },
            "repository": {
                "full_name": "testuser/testrepo"
            }
        }
        
        response = client.post(
            "/api/v1/github/webhook",
            content=json.dumps(payload),
            headers={
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    def test_webhook_with_valid_signature(self, client, github_webhook_payload, github_signature):
        """Test webhook with valid signature."""
        body = json.dumps(github_webhook_payload)
        signature = github_signature(github_webhook_payload)
        
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
        data = response.json()
        assert data["status"] == "success"
        assert data["pr_number"] == 123
        assert data["action"] == "opened"
        assert data["repository"] == "testuser/testrepo"
        assert "database_id" in data
        assert "timestamp" in data
    
    def test_webhook_non_pr_event(self, client):
        """Test webhook with non-PR event (should be ignored)."""
        payload = {"ref": "refs/heads/main"}
        
        response = client.post(
            "/api/v1/github/webhook",
            content=json.dumps(payload),
            headers={
                "X-GitHub-Event": "push",
                "Content-Type": "application/json"
            }
        )
        
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
    
    def test_webhook_pr_update(self, client, github_webhook_payload, github_signature):
        """Test webhook for updating existing PR."""
        # First webhook call (create PR)
        body = json.dumps(github_webhook_payload)
        signature = github_signature(github_webhook_payload)
        
        response1 = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        assert response1.status_code == 200
        database_id = response1.json()["database_id"]
        
        # Second webhook call with updated data (same PR number)
        updated_payload = github_webhook_payload.copy()
        updated_payload["action"] = "closed"
        updated_payload["pull_request"]["title"] = "Updated Test PR"
        
        updated_body = json.dumps(updated_payload)
        updated_signature = github_signature(updated_payload)
        
        response2 = client.post(
            "/api/v1/github/webhook",
            content=updated_body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": updated_signature,
                "Content-Type": "application/json"
            }
        )
        
        assert response2.status_code == 200
        assert response2.json()["action"] == "closed"
        # Should have the same database ID (updated existing PR)
        assert response2.json()["database_id"] == database_id