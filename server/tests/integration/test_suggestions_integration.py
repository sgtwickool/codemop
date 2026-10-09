"""
Integration tests for Suggestions API endpoint.
"""
import pytest

from app.db.session import session_scope
from app.models.suggestion import Suggestion
from tests.helpers import AUTH_HEADERS, pr_event


class TestSuggestionsIntegration:
    """Integration tests for suggestions API endpoint."""
    
    def test_get_suggestions_for_pr(self, client, post_webhook):
        """A newly stored PR has no suggestions yet."""
        pr_id = post_webhook(pr_event(title="Test PR for suggestions")).json()["database_id"]
        
        response = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH_HEADERS)
        
        assert response.status_code == 200
        data = response.json()
        assert data["pr_id"] == pr_id
        assert data["suggestions_count"] == 0
        assert data["suggestions"] == []
    
    def test_get_suggestions_with_suggestions(self, client, post_webhook):
        """A stored suggestion is returned with its fields."""
        pr_id = post_webhook(pr_event(number=456, title="Test PR with suggestions")).json()["database_id"]
        with session_scope() as db:
            db.add(Suggestion(
                pr_id=pr_id,
                line_number=42,
                file_path="test.py",
                description="Test suggestion from integration test",
                fix="test fix code",
                confidence=0.95
            ))
        
        response = client.get(f"/api/v1/pr/{pr_id}/suggestions", headers=AUTH_HEADERS)
        
        assert response.status_code == 200
        data = response.json()
        assert data["pr_id"] == pr_id
        assert data["suggestions_count"] == 1
        suggestion_data = data["suggestions"][0]
        assert suggestion_data["line_number"] == 42
        assert suggestion_data["file_path"] == "test.py"
        assert suggestion_data["description"] == "Test suggestion from integration test"
        assert suggestion_data["fix"] == "test fix code"
        assert suggestion_data["confidence"] == 0.95
    
    def test_get_suggestions_invalid_pr_id(self, client):
        response = client.get("/api/v1/pr/99999/suggestions", headers=AUTH_HEADERS)
        
        assert response.status_code == 404
        assert "detail" in response.json()
    
    def test_get_suggestions_without_authentication(self, client, post_webhook):
        pr_id = post_webhook(pr_event(number=789)).json()["database_id"]
        
        response = client.get(f"/api/v1/pr/{pr_id}/suggestions")
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    def test_get_suggestions_with_invalid_authentication(self, client, post_webhook):
        pr_id = post_webhook(pr_event(number=101)).json()["database_id"]
        
        response = client.get(
            f"/api/v1/pr/{pr_id}/suggestions", headers={"Authorization": "Bearer invalid_api_key_12345"}
        )
        
        assert response.status_code == 401
        assert "detail" in response.json()


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
