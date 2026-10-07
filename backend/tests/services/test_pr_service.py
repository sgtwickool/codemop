"""
Unit tests for PR service functions.
"""
import pytest
from app.services.pr_service import pr_service
from tests.helpers import pr_data


class TestPRService:
    """Test PR service functions."""
    
    def test_create_pr_success(self, db_session):
        pr = pr_service.create_pr(db_session, pr_data(status="open"))
        
        assert pr.number == 123
        assert pr.repo_name == "testrepo"
        assert pr.title == "Test PR"
        assert pr.status == "open"
    
    def test_create_pr_update_existing(self, db_session):
        """Saving the same repo and number again updates the PR."""
        pr1 = pr_service.create_pr(db_session, pr_data())
        pr2 = pr_service.create_pr(db_session, pr_data(status="closed", title="Updated Test PR"))
        
        assert pr1.id == pr2.id
        assert pr2.status == "closed"
        assert pr2.title == "Updated Test PR"
    
    def test_get_pr_by_id_success(self, db_session):
        created_pr = pr_service.create_pr(db_session, pr_data())
        
        retrieved_pr = pr_service.get_pr_by_id(db_session, created_pr.id)
        
        assert retrieved_pr.id == created_pr.id
        assert retrieved_pr.number == 123
        assert retrieved_pr.title == "Test PR"
    
    def test_get_pr_by_id_not_found(self, db_session):
        with pytest.raises(ValueError) as exc_info:
            pr_service.get_pr_by_id(db_session, 99999)
        
        assert "PR with ID 99999 not found" in str(exc_info.value)
    
    def test_get_pr_by_number_success(self, db_session):
        created_pr = pr_service.create_pr(db_session, pr_data(number=456))
        
        retrieved_pr = pr_service.get_pr_by_number(db_session, "testuser/testrepo", 456)
        
        assert retrieved_pr.id == created_pr.id
        assert retrieved_pr.number == 456
        assert retrieved_pr.title == "Test PR"
    
    def test_get_pr_by_number_not_found(self, db_session):
        with pytest.raises(ValueError) as exc_info:
            pr_service.get_pr_by_number(db_session, "testuser/testrepo", 99999)
        
        assert "PR testuser/testrepo#99999 not found" in str(exc_info.value)
    
    def test_same_number_in_different_repos_are_different_prs(self, db_session):
        """PR numbers restart in every repo, so #1 in one repo mustn't overwrite #1 in another."""
        def first_pr_in(repo):
            return pr_data(number=1, repo_name=repo.split("/")[1], repo_full_name=repo, title=f"First PR in {repo}")
        
        first = pr_service.create_pr(db_session, first_pr_in("owner/repo-a"))
        second = pr_service.create_pr(db_session, first_pr_in("owner/repo-b"))
        
        assert first.id != second.id
        assert pr_service.get_pr_by_number(db_session, "owner/repo-a", 1).title == "First PR in owner/repo-a"
        assert pr_service.get_pr_by_number(db_session, "owner/repo-b", 1).title == "First PR in owner/repo-b"
