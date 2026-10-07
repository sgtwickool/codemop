from typing import List
from sqlalchemy.orm import Session
from app.models.suggestion import Suggestion
from app.db.base import BaseRepository

class SuggestionRepository(BaseRepository[Suggestion]):
    """Suggestion repository with specific operations"""
    
    def __init__(self):
        super().__init__(Suggestion)
    
    def get_by_pr_id(self, db: Session, pr_id: int) -> List[Suggestion]:
        """Get all suggestions for a specific PR"""
        return db.query(Suggestion).filter(Suggestion.pr_id == pr_id).all()
    
    def delete_by_pr_id(self, db: Session, pr_id: int) -> int:
        """Delete all suggestions for a PR; returns how many"""
        return db.query(Suggestion).filter(Suggestion.pr_id == pr_id).delete()

suggestion_repository = SuggestionRepository()