from typing import List, Dict, Any, Optional
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
        suggestions: List[Dict[str, Any]],
        head_sha: Optional[str],
    ) -> List[Suggestion]:
        """
        Replace a PR's suggestions with those from a new analysis of `head_sha`.
        
        `suggestions` are complete, as returned by parse_ai_response. Doesn't commit, so the
        caller can make the swap atomic.
        """
        suggestion_repository.delete_by_pr_id(db, pr.id)
        created = [Suggestion(pr_id=pr.id, **suggestion) for suggestion in suggestions]
        db.add_all(created)
        pr.analyzed_sha = head_sha
        db.flush()  # assigns IDs, and lets this session see the new suggestions
        return created

suggestion_service = SuggestionService()
