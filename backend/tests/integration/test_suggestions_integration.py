"""
Integration tests for Suggestions API endpoint.
"""
import pytest
import json

from tests.helpers import AUTH_HEADERS, pr_event


class TestSuggestionsIntegration:
    """Integration tests for suggestions API endpoint."""
    
    def test_get_suggestions_for_pr(self, client):
        """Test getting suggestions for a specific PR."""
        # First, create a PR via webhook to have data in the database
        payload = {
            "action": "opened",
            "number": 123,
            "pull_request": {
                "title": "Test PR for suggestions",
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
        
        # Now test getting suggestions for this PR (should be empty initially)
        response = client.get(
            f"/api/v1/pr/{pr_id}/suggestions",
            headers={
                "Authorization": "Bearer test_api_key"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["pr_id"] == pr_id
        assert data["suggestions_count"] == 0
        assert data["suggestions"] == []
    
    def test_get_suggestions_with_suggestions(self, client):
        """Test getting suggestions when PR has suggestions."""
        # This test would need AI analysis to be mocked or actually run
        # For now, we'll test the basic structure
        
        # First create a PR
        payload = {
            "action": "opened",
            "number": 456,
            "pull_request": {
                "title": "Test PR with suggestions",
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
        
        # Manually add a suggestion to the database for testing
        from app.models.suggestion import Suggestion
        from app.db.session import get_db
        
        db = next(get_db())
        try:
            suggestion = Suggestion(
                pr_id=pr_id,
                line_number=42,
                file_path="test.py",
                description="Test suggestion from integration test",
                fix="test fix code",
                confidence=0.95
            )
            db.add(suggestion)
            db.commit()
            db.refresh(suggestion)
        finally:
            db.close()
        
        # Now test getting suggestions
        response = client.get(
            f"/api/v1/pr/{pr_id}/suggestions",
            headers={
                "Authorization": "Bearer test_api_key"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["pr_id"] == pr_id
        assert data["suggestions_count"] == 1
        assert len(data["suggestions"]) == 1
        
        suggestion_data = data["suggestions"][0]
        assert suggestion_data["line_number"] == 42
        assert suggestion_data["file_path"] == "test.py"
        assert suggestion_data["description"] == "Test suggestion from integration test"
        assert suggestion_data["fix"] == "test fix code"
        assert suggestion_data["confidence"] == 0.95
    
    def test_get_suggestions_invalid_pr_id(self, client):
        """Test getting suggestions for non-existent PR."""
        response = client.get(
            "/api/v1/pr/99999/suggestions",
            headers={
                "Authorization": "Bearer test_api_key"
            }
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
    
    def test_get_suggestions_without_authentication(self, client):
        """Test getting suggestions without API key."""
        # First create a PR
        payload = {
            "action": "opened",
            "number": 789,
            "pull_request": {
                "title": "Test PR",
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
        
        # Test without authentication
        response = client.get(f"/api/v1/pr/{pr_id}/suggestions")
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    def test_get_suggestions_with_invalid_authentication(self, client):
        """Test getting suggestions with invalid API key."""
        # First create a PR
        payload = {
            "action": "opened",
            "number": 101,
            "pull_request": {
                "title": "Test PR",
                "user": {"login": "testuser"},
                "head": {"ref": "test-branch"},
                "html_url": "https://github.com/testuser/testrepo/pull/101",
                "diff_url": "https://github.com/testuser/testrepo/pull/101.diff"
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
        
        # Test with invalid API key
        response = client.get(
            f"/api/v1/pr/{pr_id}/suggestions",
            headers={
                "Authorization": "Bearer invalid_api_key_12345"
            }
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

class TestSuggestionsByRepoAndNumber:
    """GET /repos/{owner}/{repo}/pulls/{number}/suggestions"""

    def test_finds_the_pr_in_the_right_repo(self, client, post_webhook):
        post_webhook(pr_event("edited", repo="owner/repo-a", number=1, title="PR in repo A"))
        post_webhook(pr_event("edited", repo="owner/repo-b", number=1, title="PR in repo B"))

        response = client.get("/api/v1/repos/owner/repo-b/pulls/1/suggestions", headers=AUTH_HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert data["repo"] == "owner/repo-b"
        assert data["number"] == 1
        assert data["title"] == "PR in repo B"
        assert data["suggestions"] == []

    def test_same_response_as_lookup_by_id(self, client, post_webhook):
        post_webhook(pr_event("edited", repo="owner/my.repo_name-2", number=7))

        by_number = client.get("/api/v1/repos/owner/my.repo_name-2/pulls/7/suggestions", headers=AUTH_HEADERS).json()
        by_id = client.get(f"/api/v1/pr/{by_number['pr_id']}/suggestions", headers=AUTH_HEADERS).json()

        assert by_number == by_id

    def test_unknown_pr_is_404(self, client):
        response = client.get("/api/v1/repos/owner/repo/pulls/999/suggestions", headers=AUTH_HEADERS)

        assert response.status_code == 404
        assert response.json()["detail"] == "PR owner/repo#999 not found"

    def test_requires_api_key(self, client):
        response = client.get("/api/v1/repos/owner/repo/pulls/1/suggestions")

        assert response.status_code == 401

    @pytest.mark.parametrize("path", [
        "/api/v1/repos/owner/repo/pulls/0/suggestions",
        "/api/v1/repos/owner/repo/pulls/abc/suggestions",
        "/api/v1/repos/own%20er/repo/pulls/1/suggestions",
    ])
    def test_invalid_paths_are_rejected(self, client, path):
        assert client.get(path, headers=AUTH_HEADERS).status_code == 422
