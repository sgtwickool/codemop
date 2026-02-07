"""
Unit tests for GitHub service functions.
"""
import pytest
from app.services.github import (
    validate_github_webhook_signature,
    extract_pr_data,
    extract_pr_metadata,
    _get_pr_payload_data
)
import hmac
import hashlib
import json


class TestGitHubService:
    """Test GitHub service functions."""
    
    def test_get_pr_payload_data(self, github_webhook_payload):
        """Test the helper function for extracting payload data."""
        action, pr_number, pr_data, repo_data = _get_pr_payload_data(github_webhook_payload)
        
        assert action == "opened"
        assert pr_number == 123
        assert "title" in pr_data
        assert "full_name" in repo_data
    
    def test_extract_pr_data(self, github_webhook_payload):
        """Test PR data extraction for database."""
        pr_data = extract_pr_data(github_webhook_payload)
        
        assert pr_data["github_id"] == 123
        assert pr_data["repo_name"] == "testrepo"
        assert pr_data["repo_full_name"] == "testuser/testrepo"
        assert pr_data["branch"] == "test-branch"
        assert pr_data["author"] == "testuser"
        assert pr_data["title"] == "Test PR"
        assert pr_data["status"] == "opened"
        assert pr_data["github_url"] == "https://github.com/testuser/testrepo/pull/123"
        assert pr_data["diff_url"] == "https://github.com/testuser/testrepo/pull/123.diff"
    
    def test_extract_pr_metadata(self, github_webhook_payload):
        """Test PR metadata extraction for logging."""
        metadata = extract_pr_metadata(github_webhook_payload)
        
        assert metadata["action"] == "opened"
        assert metadata["pr_number"] == 123
        assert "title" in metadata["pr_data"]
        assert "full_name" in metadata["repo_data"]
    
    @pytest.mark.asyncio
    async def test_validate_github_webhook_signature_valid(self):
        """Test valid GitHub webhook signature validation."""
        # Use the actual secret from settings
        from app.config import settings
        
        payload = {"action": "opened", "number": 123}
        body = json.dumps(payload)
        secret = settings.GITHUB_WEBHOOK_SECRET
        signature = "sha256=" + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        
        # Should not raise an exception
        await validate_github_webhook_signature(body.encode(), signature)
    
    @pytest.mark.asyncio
    async def test_validate_github_webhook_signature_invalid(self):
        """Test invalid GitHub webhook signature validation."""
        payload = {"action": "opened", "number": 123}
        body = json.dumps(payload)
        
        # Should raise HTTPException for invalid signature
        with pytest.raises(Exception) as exc_info:
            await validate_github_webhook_signature(body.encode(), "invalid_signature")
        
        assert "Invalid signature" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validate_github_webhook_signature_missing(self):
        """Test missing GitHub webhook signature validation."""
        payload = {"action": "opened", "number": 123}
        body = json.dumps(payload)
        
        # Should raise HTTPException for missing signature
        with pytest.raises(Exception) as exc_info:
            await validate_github_webhook_signature(body.encode(), None)
        
        assert "Missing signature" in str(exc_info.value)
    
    def test_extract_pr_data_missing_fields(self):
        """Test PR data extraction with missing fields."""
        minimal_payload = {
            "action": "opened",
            "number": 456,
            "pull_request": {},
            "repository": {}
        }
        
        pr_data = extract_pr_data(minimal_payload)
        
        assert pr_data["github_id"] == 456
        assert pr_data["repo_name"] is None
        assert pr_data["branch"] is None
        assert pr_data["author"] is None
        assert pr_data["title"] is None
        assert pr_data["status"] == "opened"
        assert pr_data["github_url"] is None
        assert pr_data["diff_url"] is None