from typing import Dict, Any
from sqlalchemy.orm import Session
from app.models.pr import PR
from app.db.pr_repository import pr_repository
import logging

logger = logging.getLogger(__name__)

class PRService:
    """PR business logic service"""
    
    def create_pr(self, db: Session, pr_data: Dict[str, Any]) -> PR:
        """Create a new PR record, or update the existing one for this repo and number"""
        try:
            pr_record = pr_repository.upsert(db, pr_data)
            logger.info(
                f"Saved PR {pr_data['repo_full_name']}#{pr_data['number']} with ID {pr_record.id}"
            )
            return pr_record
        except Exception as e:
            logger.error(f"Failed to store PR data: {str(e)}")
            raise
    
    def get_pr_by_id(self, db: Session, pr_id: int) -> PR:
        """Get PR by database ID"""
        pr = pr_repository.get(db, pr_id)
        if not pr:
            raise ValueError(f"PR with ID {pr_id} not found")
        return pr
    
    def get_pr_by_number(self, db: Session, repo_full_name: str, number: int) -> PR:
        """Get PR by repository and PR number"""
        pr = pr_repository.get_by_number(db, repo_full_name, number)
        if not pr:
            raise ValueError(f"PR {repo_full_name}#{number} not found")
        return pr

pr_service = PRService()
