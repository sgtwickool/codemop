from typing import Dict, Any
from sqlalchemy.orm import Session
from app.models.pr import PR
from app.db.pr_repository import pr_repository
import logging

logger = logging.getLogger(__name__)

class PRService:
    """PR business logic service"""
    
    def create_pr(self, db: Session, pr_data: Dict[str, Any]) -> PR:
        """Create a new PR record or update existing one"""
        try:
            # Check if PR already exists
            existing_pr = pr_repository.get_by_github_id(db, pr_data['github_id'])
            if existing_pr:
                # Update existing PR
                pr_record = pr_repository.update(db, existing_pr, pr_data)
                logger.info(f"Updated existing PR #{pr_data['github_id']} with ID {pr_record.id}")
            else:
                # Create new PR
                pr_record = pr_repository.create(db, pr_data)
                logger.info(f"Stored PR #{pr_data['github_id']} in database with ID {pr_record.id}")
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
    
    def get_pr_by_github_id(self, db: Session, github_id: int) -> PR:
        """Get PR by GitHub ID"""
        pr = pr_repository.get_by_github_id(db, github_id)
        if not pr:
            raise ValueError(f"PR with GitHub ID {github_id} not found")
        return pr

pr_service = PRService()