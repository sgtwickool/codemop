from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.pr import PR
from app.models.suggestion import Suggestion
from app.db.suggestion_repository import suggestion_repository
import logging

logger = logging.getLogger(__name__)

class SuggestionService:
    """Suggestion business logic service"""
    
    def create_suggestion(self, db: Session, suggestion_data: Dict[str, Any]) -> Suggestion:
        """Create a new suggestion record"""
        try:
            # Set default values for optional fields
            if "fix" not in suggestion_data or suggestion_data["fix"] is None:
                suggestion_data["fix"] = "No fix provided"
            if "confidence" not in suggestion_data or suggestion_data["confidence"] is None:
                suggestion_data["confidence"] = 0.5
            
            suggestion = suggestion_repository.create(db, suggestion_data)
            logger.debug(f"Created suggestion {suggestion.id} for PR {suggestion.pr_id}")
            return suggestion
        except Exception as e:
            logger.error(f"Failed to create suggestion: {str(e)}")
            raise
    
    def get_suggestions_by_pr_id(self, db: Session, pr_id: int) -> List[Suggestion]:
        """Get all suggestions for a specific PR"""
        return suggestion_repository.get_by_pr_id(db, pr_id)
    
    def create_suggestions_batch(self, db: Session, pr_id: int, suggestions: List[Dict[str, Any]]) -> List[Suggestion]:
        """Create multiple suggestions for a PR"""
        created_suggestions = []
        for suggestion in suggestions:
            suggestion_data = {
                "pr_id": pr_id,
                "line_number": suggestion.get("line_number"),
                "file_path": suggestion.get("file_path"),
                "description": suggestion.get("description"),
                "fix": suggestion.get("fix"),
                "confidence": suggestion.get("confidence")
            }
            try:
                created_suggestion = self.create_suggestion(db, suggestion_data)
                created_suggestions.append(created_suggestion)
            except Exception as e:
                logger.error(f"Failed to create suggestion: {str(e)}")
                # Continue with other suggestions even if one fails
                continue
        
        return created_suggestions

    def replace_for_pr(
        self,
        db: Session,
        pr: PR,
        suggestions: List[Dict[str, Any]],
        head_sha: Optional[str],
    ) -> List[Suggestion]:
        """
        Replace a PR's suggestions with those from a new analysis of `head_sha`.
        
        Doesn't commit, so the caller can make the swap atomic.
        """
        db.query(Suggestion).filter(Suggestion.pr_id == pr.id).delete()
        
        created = []
        for suggestion in suggestions:
            if not suggestion.get("description") or not suggestion.get("file_path") or suggestion.get("line_number") is None:
                logger.warning(f"Skipping incomplete suggestion for PR {pr.id}: {suggestion}")
                continue
            created.append(Suggestion(
                pr_id=pr.id,
                line_number=suggestion["line_number"],
                file_path=suggestion["file_path"],
                description=suggestion["description"],
                fix=suggestion.get("fix") or "No fix provided",
                confidence=suggestion.get("confidence", 0.5),
                head_sha=head_sha,
            ))
        db.add_all(created)
        pr.analyzed_sha = head_sha
        return created

suggestion_service = SuggestionService()