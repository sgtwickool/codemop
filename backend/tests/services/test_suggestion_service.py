"""
Unit tests for Suggestion service functions.
"""
from app.services.pr_service import pr_service
from app.services.suggestion_service import suggestion_service
from tests.helpers import pr_data


def suggestion(description, line_number=10):
    return {
        "line_number": line_number,
        "file_path": "app.py",
        "description": description,
        "fix": "fixed()",
        "confidence": 0.9,
    }


class TestSuggestionService:
    """Test Suggestion service functions."""

    def test_no_suggestions_for_a_new_pr(self, db_session):
        pr = pr_service.create_pr(db_session, pr_data())

        assert suggestion_service.get_suggestions_by_pr_id(db_session, pr.id) == []

    def test_replace_stores_suggestions_and_the_analysed_commit(self, db_session):
        pr = pr_service.create_pr(db_session, pr_data())

        suggestion_service.replace_for_pr(db_session, pr, [suggestion("First"), suggestion("Second", 20)], "a" * 40)

        stored = suggestion_service.get_suggestions_by_pr_id(db_session, pr.id)
        assert sorted(s.description for s in stored) == ["First", "Second"]
        assert stored[0].file_path == "app.py"
        assert pr.analyzed_sha == "a" * 40

    def test_replace_removes_earlier_suggestions(self, db_session):
        pr = pr_service.create_pr(db_session, pr_data())
        suggestion_service.replace_for_pr(db_session, pr, [suggestion("Old")], "a" * 40)

        suggestion_service.replace_for_pr(db_session, pr, [suggestion("New")], "b" * 40)

        stored = suggestion_service.get_suggestions_by_pr_id(db_session, pr.id)
        assert [s.description for s in stored] == ["New"]
        assert pr.analyzed_sha == "b" * 40

    def test_suggestions_are_kept_per_pr(self, db_session):
        first = pr_service.create_pr(db_session, pr_data(number=1))
        second = pr_service.create_pr(db_session, pr_data(number=2))

        suggestion_service.replace_for_pr(db_session, first, [suggestion("For the first PR")], "a" * 40)

        assert suggestion_service.get_suggestions_by_pr_id(db_session, second.id) == []

    def test_replace_doesnt_commit(self, db_session):
        """The caller owns the transaction, so the swap can be atomic."""
        pr = pr_service.create_pr(db_session, pr_data())
        db_session.commit()
        suggestion_service.replace_for_pr(db_session, pr, [suggestion("Uncommitted")], "a" * 40)

        db_session.rollback()

        assert suggestion_service.get_suggestions_by_pr_id(db_session, pr.id) == []
