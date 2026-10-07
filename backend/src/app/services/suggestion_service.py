from typing import List, Optional
from codemop.review.schema import ModelSuggestion
from sqlalchemy.orm import Session
from app.models.pr import PR
from app.models.suggestion import Suggestion
from app.db.suggestion_repository import suggestion_repository

class SuggestionService:
    """Suggestion business logic service"""
    
    def get_suggestions_by_pr_id(self, db: Session, pr_id: int) -> List[Suggestion]:
        """Get all suggestions for a specific PR"""
        return suggestion_repository.get_by_pr_id(db, pr_id)
    
    def replace_for_pr(
        self,
        db: Session,
        pr: PR,
        suggestions: List[ModelSuggestion],
        head_sha: Optional[str],
    ) -> List[Suggestion]:
        """
        Replace a PR's suggestions with those from a new review of `head_sha`.
        
        `suggestions` come from codemop's review (validated, and on lines GitHub can comment
        on). Doesn't commit, so the caller can make the swap atomic.
        """
        suggestion_repository.delete_by_pr_id(db, pr.id)
        created = [
            Suggestion(
                pr_id=pr.id,
                file_path=s.file_path,
                line_number=s.line,
                end_line=s.end_line,
                severity=s.severity.value,
                title=s.title,
                description=s.explanation,
                fix=s.suggested_code,
                confidence=s.confidence,
            )
            for s in suggestions
        ]
        db.add_all(created)
        pr.analyzed_sha = head_sha
        db.flush()  # assigns IDs, and lets this session see the new suggestions
        return created

suggestion_service = SuggestionService()
