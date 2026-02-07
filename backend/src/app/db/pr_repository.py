from typing import Optional
from sqlalchemy.orm import Session
from app.models.pr import PR
from app.db.base import BaseRepository

class PRRepository(BaseRepository[PR]):
    """PR repository with specific operations"""
    
    def __init__(self):
        super().__init__(PR)
    
    def get_by_github_id(self, db: Session, github_id: int) -> Optional[PR]:
        """Get PR by GitHub ID"""
        return self.get_by_field(db, "github_id", github_id)
    
    def update_status(self, db: Session, github_id: int, status: str) -> Optional[PR]:
        """Update PR status"""
        pr = self.get_by_github_id(db, github_id)
        if pr:
            return self.update(db, pr, {"status": status})
        return None

pr_repository = PRRepository()