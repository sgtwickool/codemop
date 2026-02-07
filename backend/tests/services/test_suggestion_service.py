"""
Unit tests for Suggestion service functions.
"""
import pytest
from app.services.suggestion_service import suggestion_service
from app.models.suggestion import Suggestion
from app.models.pr import PR


class TestSuggestionService:
    """Test Suggestion service functions."""
    
    def test_create_suggestion_success(self, db_session):
        """Test successful suggestion creation."""
        # First create a PR for the suggestion to belong to
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
        
        from app.services.pr_service import pr_service
        pr = pr_service.create_pr(db_session, pr_data)
        
        # Now create a suggestion for this PR
        suggestion_data = {
            "pr_id": pr.id,
            "line_number": 42,
            "file_path": "test.py",
            "description": "Test suggestion description",
            "fix": "Test fix code",
            "confidence": 0.95
        }
        
        suggestion = suggestion_service.create_suggestion(db_session, suggestion_data)
        
        assert suggestion.pr_id == pr.id
        assert suggestion.line_number == 42
        assert suggestion.file_path == "test.py"
        assert suggestion.description == "Test suggestion description"
        assert suggestion.fix == "Test fix code"
        assert suggestion.confidence == 0.95
    
    def test_create_suggestion_batch(self, db_session):
        """Test creating multiple suggestions at once."""
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
        
        from app.services.pr_service import pr_service
        pr = pr_service.create_pr(db_session, pr_data)
        
        # Create multiple suggestions
        suggestions_data = [
            {
                "line_number": 10,
                "file_path": "file1.py",
                "description": "First suggestion",
                "fix": "First fix",
                "confidence": 0.90
            },
            {
                "line_number": 20,
                "file_path": "file2.py",
                "description": "Second suggestion",
                "fix": "Second fix",
                "confidence": 0.85
            },
            {
                "line_number": 30,
                "file_path": "file3.py",
                "description": "Third suggestion",
                "fix": "Third fix",
                "confidence": 0.80
            }
        ]
        
        created_suggestions = suggestion_service.create_suggestions_batch(
            db_session, pr.id, suggestions_data
        )
        
        assert len(created_suggestions) == 3
        assert created_suggestions[0].line_number == 10
        assert created_suggestions[1].line_number == 20
        assert created_suggestions[2].line_number == 30
        
        # Verify all suggestions belong to the same PR
        for suggestion in created_suggestions:
            assert suggestion.pr_id == pr.id
    
    def test_get_suggestions_by_pr_id(self, db_session):
        """Test getting suggestions for a specific PR."""
        # Create a PR first
        pr_data = {
            "github_id": 789,
            "repo_name": "testrepo",
            "repo_full_name": "testuser/testrepo",
            "branch": "test-branch",
            "author": "testuser",
            "title": "Test PR",
            "status": "opened",
            "github_url": "https://github.com/testuser/testrepo/pull/789",
            "diff_url": "https://github.com/testuser/testrepo/pull/789.diff"
        }
        
        from app.services.pr_service import pr_service
        pr = pr_service.create_pr(db_session, pr_data)
        
        # Create some suggestions
        suggestion1 = suggestion_service.create_suggestion(db_session, {
            "pr_id": pr.id,
            "line_number": 10,
            "file_path": "test.py",
            "description": "First suggestion",
            "fix": "First fix",
            "confidence": 0.90
        })
        
        suggestion2 = suggestion_service.create_suggestion(db_session, {
            "pr_id": pr.id,
            "line_number": 20,
            "file_path": "test.py",
            "description": "Second suggestion",
            "fix": "Second fix",
            "confidence": 0.85
        })
        
        # Get suggestions for this PR
        suggestions = suggestion_service.get_suggestions_by_pr_id(db_session, pr.id)
        
        assert len(suggestions) == 2
        assert suggestions[0].id == suggestion1.id
        assert suggestions[1].id == suggestion2.id
    
    def test_get_suggestions_by_pr_id_empty(self, db_session):
        """Test getting suggestions for PR with no suggestions."""
        # Create a PR first
        pr_data = {
            "github_id": 999,
            "repo_name": "testrepo",
            "repo_full_name": "testuser/testrepo",
            "branch": "test-branch",
            "author": "testuser",
            "title": "Test PR",
            "status": "opened",
            "github_url": "https://github.com/testuser/testrepo/pull/999",
            "diff_url": "https://github.com/testuser/testrepo/pull/999.diff"
        }
        
        from app.services.pr_service import pr_service
        pr = pr_service.create_pr(db_session, pr_data)
        
        # Get suggestions for PR with no suggestions
        suggestions = suggestion_service.get_suggestions_by_pr_id(db_session, pr.id)
        
        assert len(suggestions) == 0
        assert suggestions == []
    
    def test_create_suggestion_with_missing_fields(self, db_session):
        """Test creating suggestion with missing optional fields."""
        # Create a PR first
        pr_data = {
            "github_id": 111,
            "repo_name": "testrepo",
            "repo_full_name": "testuser/testrepo",
            "branch": "test-branch",
            "author": "testuser",
            "title": "Test PR",
            "status": "opened",
            "github_url": "https://github.com/testuser/testrepo/pull/111",
            "diff_url": "https://github.com/testuser/testrepo/pull/111.diff"
        }
        
        from app.services.pr_service import pr_service
        pr = pr_service.create_pr(db_session, pr_data)
        
        # Create suggestion with minimal data
        suggestion_data = {
            "pr_id": pr.id,
            "line_number": 5,
            "file_path": "minimal.py",
            "description": "Minimal suggestion"
            # Missing: fix, confidence (should use defaults)
        }
        
        suggestion = suggestion_service.create_suggestion(db_session, suggestion_data)
        
        assert suggestion.pr_id == pr.id
        assert suggestion.line_number == 5
        assert suggestion.description == "Minimal suggestion"
        # Should have default values for missing fields
        assert suggestion.fix is not None
        assert suggestion.confidence is not None