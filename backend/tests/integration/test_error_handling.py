"""
Integration tests for error handling scenarios.
"""
import pytest
import json
from unittest.mock import AsyncMock, patch


class TestErrorHandlingIntegration:
    """Integration tests for error handling."""

    def test_database_connection_failure_webhook(self, client):
        """Test webhook handling when database connection fails."""
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
        
        # Mock database to raise connection error
        with patch('app.services.pr_service.pr_service.create_pr') as mock_create_pr:
            mock_create_pr.side_effect = Exception("Database connection failed")
            
            response = client.post(
                "/api/v1/github/webhook",
                content=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": signature,
                    "Content-Type": "application/json"
                }
            )
            
            # Should return 500 error
            assert response.status_code == 500
            data = response.json()
            assert "detail" in data
            assert "Database error" in data["detail"]

    def test_network_failure_ai_api(self, client):
        """Test handling of AI API network failures."""
        payload = {
            "action": "opened",
            "number": 456,
            "pull_request": {
                "title": "Test PR with AI failure",
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
        
        # Mock AI analysis to fail
        failing_ai = AsyncMock(side_effect=Exception("AI API network timeout"))
        with patch('app.services.pr_analysis.analyze_pr_with_ai', new=failing_ai):
            
            response = client.post(
                "/api/v1/github/webhook",
                content=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": signature,
                    "Content-Type": "application/json"
                }
            )
            
            # Analysis runs after the response, so its failure can't break the webhook
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["analysis"] == "queued"
            failing_ai.assert_awaited_once()

    def test_network_failure_github_diff(self, client):
        """Test handling of GitHub diff fetch failures."""
        payload = {
            "action": "opened",
            "number": 789,
            "pull_request": {
                "title": "Test PR with GitHub failure",
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
        
        # Mock GitHub diff fetch to fail
        failing_fetch = AsyncMock(side_effect=Exception("GitHub API unavailable"))
        with patch('app.services.ai_analysis.fetch_diff_content', new=failing_fetch):
            
            response = client.post(
                "/api/v1/github/webhook",
                content=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": signature,
                    "Content-Type": "application/json"
                }
            )
            
            # Analysis runs after the response, so its failure can't break the webhook
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["analysis"] == "queued"
            failing_fetch.assert_awaited_once()

    def test_invalid_pr_data_missing_fields(self, client):
        """PR events without the data needed to store the PR are rejected, not a 500."""
        # Minimal payload with missing fields
        payload = {
            "action": "opened",
            "number": 999,
            "pull_request": {},  # Empty PR data
            "repository": {}     # Empty repo data
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
        
        assert response.status_code == 422
        assert "missing required fields" in response.json()["detail"]

    def test_invalid_suggestion_data(self, client):
        """Test handling of invalid suggestion data."""
        # First create a PR
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
        
        # Now test suggestions endpoint with this PR
        response = client.get(
            f"/api/v1/pr/{pr_id}/suggestions",
            headers={
                "Authorization": "Bearer test_api_key"
            }
        )
        
        # Should return 200 even with no suggestions
        assert response.status_code == 200
        data = response.json()
        assert data["suggestions_count"] == 0

    def test_malformed_json_webhook(self, client, github_signature):
        """Test handling of malformed JSON in webhook."""
        response = client.post(
            "/api/v1/github/webhook",
            content="{invalid json",
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": github_signature("{invalid json"),
                "Content-Type": "application/json"
            }
        )
        
        # Should return 422 (Unprocessable Entity)
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_malformed_json_suggestions(self, client):
        """Test handling of malformed JSON in suggestions endpoint."""
        response = client.get(
            "/api/v1/pr/999/suggestions",
            headers={
                "Authorization": "Bearer test_api_key",
                "Content-Type": "application/json"
            }
        )
        
        # Should return 404 (PR not found) not JSON error
        assert response.status_code == 404

    def test_internal_server_error_handling(self, client):
        """Test handling of unexpected internal server errors."""
        # Try to access a non-existent endpoint
        response = client.get("/api/v1/nonexistent")
        
        # Should return 404
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_error_response_format(self, client):
        """Test that error responses have consistent format."""
        error_scenarios = [
            {
                "endpoint": "/api/v1/pr/999/suggestions",
                "method": "GET",
                "headers": {"Authorization": "Bearer test_api_key"},
                "expected_status": 404
            },
            {
                "endpoint": "/api/v1/pr/999/suggestions",
                "method": "GET",
                "headers": {},
                "expected_status": 401
            },
            {
                "endpoint": "/api/v1/nonexistent",
                "method": "GET",
                "headers": {},
                "expected_status": 404
            }
        ]
        
        for scenario in error_scenarios:
            if scenario["method"] == "GET":
                response = client.get(scenario["endpoint"], headers=scenario["headers"])
            else:
                response = client.post(scenario["endpoint"], headers=scenario["headers"])
            
            assert response.status_code == scenario["expected_status"]
            data = response.json()
            assert "detail" in data
            assert isinstance(data["detail"], str)

    def test_error_recovery_after_failure(self, client):
        """Test that system recovers properly after errors."""
        # First cause an error
        response = client.get("/api/v1/pr/999/suggestions")
        assert response.status_code == 401  # Unauthorized
        
        # Then make a valid request
        payload = {
            "action": "opened",
            "number": 333,
            "pull_request": {
                "title": "Test PR after error",
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
        
        response = client.post(
            "/api/v1/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json"
            }
        )
        
        # Should work fine after previous error
        assert response.status_code == 200