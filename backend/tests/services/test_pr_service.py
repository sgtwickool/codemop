"""
Unit tests for PR service functions.
"""
import pytest
from app.services.pr_service import pr_service
from app.models.pr import PR


class TestPRService:
    """Test PR service functions."""
    
    def test_create_pr_success(self, db_session):
        """Test successful PR creation."""
        pr_data = {
            "github_id": 123,
            "repo_name": "testrepo",
            "repo_full_name": "testuser/testrepo",
            "branch": "test-branch",
            "author": "testuser",
            "title": "Test PR",
            "status": "opened",
            "github_url": "https://github.com/testuser/testrepo/pull/123",
            "diff_url": "https://github.com/testuser/testrepo/pull/123.diff"
        }
        
        pr = pr_service.create_pr(db_session, pr_data)
        
        assert pr.github_id == 123
        assert pr.repo_name == "testrepo"
        assert pr.title == "Test PR"
        assert pr.status == "opened"
    
    def test_create_pr_update_existing(self, db_session):
        """Test updating existing PR."""
        # Create initial PR
        pr_data = {
            "github_id": 123,
            "repo_name": "testrepo",
            "repo_full_name": "testuser/testrepo",
            "branch": "test-branch",
            "author": "testuser",
            "title": "Test PR",
            "status": "opened",
            "github_url": "https://github.com/testuser/testrepo/pull/123",
            "diff_url": "https://github.com/testuser/testrepo/pull/123.diff"
        }
        
        pr1 = pr_service.create_pr(db_session, pr_data)
        
        # Update the same PR
        updated_data = pr_data.copy()
        updated_data["status"] = "closed"
        updated_data["title"] = "Updated Test PR"
        
        pr2 = pr_service.create_pr(db_session, updated_data)
        
        assert pr1.id == pr2.id  # Same PR ID
        assert pr2.status == "closed"  # Status updated
        assert pr2.title == "Updated Test PR"  # Title updated
    
    def test_get_pr_by_id_success(self, db_session):
        """Test getting PR by ID."""
        # Create a PR first
        pr_data = {
            "github_id": 123,
            "repo_name": "testrepo",
            "repo_full_name": "testuser/testrepo",
            "branch": "test-branch",
            "author": "testuser",
            "title": "Test PR",
            "status": "opened",
            "github_url": "https://github.com/testuser/testrepo/pull/123",
            "diff_url": "https://github.com/testuser/testrepo/pull/123.diff"
        }
        
        created_pr = pr_service.create_pr(db_session, pr_data)
        
        # Get the PR by ID
        retrieved_pr = pr_service.get_pr_by_id(db_session, created_pr.id)
        
        assert retrieved_pr.id == created_pr.id
        assert retrieved_pr.github_id == 123
        assert retrieved_pr.title == "Test PR"
    
    def test_get_pr_by_id_not_found(self, db_session):
        """Test getting non-existent PR by ID."""
        with pytest.raises(ValueError) as exc_info:
            pr_service.get_pr_by_id(db_session, 99999)
        
        assert "PR with ID 99999 not found" in str(exc_info.value)
    
    def test_get_pr_by_github_id_success(self, db_session):
        """Test getting PR by GitHub ID."""
        # Create a PR first
        pr_data = {
            "github_id": 456,
            "repo_name": "testrepo",
            "repo_full_name": "testuser/testrepo",
            "branch": "test-branch",
            "author": "testuser",
            "title": "Test PR",
            "status": "opened",
            "github_url": "https://github.com/testuser/testrepo/pull/456",
            "diff_url": "https://github.com/testuser/testrepo/pull/456.diff"
        }
        
        created_pr = pr_service.create_pr(db_session, pr_data)
        
        # Get the PR by GitHub ID
        retrieved_pr = pr_service.get_pr_by_github_id(db_session, 456)
        
        assert retrieved_pr.id == created_pr.id
        assert retrieved_pr.github_id == 456
        assert retrieved_pr.title == "Test PR"
    
    def test_get_pr_by_github_id_not_found(self, db_session):
        """Test getting non-existent PR by GitHub ID."""
        with pytest.raises(ValueError) as exc_info:
            pr_service.get_pr_by_github_id(db_session, 99999)
        
        assert "PR with GitHub ID 99999 not found" in str(exc_info.value)