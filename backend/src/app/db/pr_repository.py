from typing import Any, Dict, Optional
from sqlalchemy import func
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session
from app.models.pr import PR
from app.db.base import BaseRepository

# Dialects whose INSERT supports ON CONFLICT ... DO UPDATE
_UPSERT_INSERTS = {
    "postgresql": postgresql.insert,
    "sqlite": sqlite.insert,
}

class PRRepository(BaseRepository[PR]):
    """PR repository with specific operations"""
    
    def __init__(self):
        super().__init__(PR)
    
    def get_by_number(self, db: Session, repo_full_name: str, number: int) -> Optional[PR]:
        """Get a PR by repository and PR number"""
        return (
            db.query(PR)
            .filter(PR.repo_full_name == repo_full_name, PR.number == number)
            .first()
        )
    
    def upsert(self, db: Session, pr_data: Dict[str, Any]) -> PR:
        """
        Insert a PR, or update it if the repo already has a PR with this number.
        
        This is a single statement, so concurrent webhook deliveries for the same PR
        can't both try to insert it.
        """
        dialect = db.get_bind().dialect.name
        if dialect not in _UPSERT_INSERTS:
            raise NotImplementedError(f"PR upsert is not supported on {dialect}; use PostgreSQL or SQLite")
        
        statement = _UPSERT_INSERTS[dialect](PR).values(**pr_data)
        updates = {
            column: statement.excluded[column]
            for column in pr_data
            if column not in ("repo_full_name", "number")
        }
        updates["updated_at"] = func.now()  # onupdate doesn't fire for ON CONFLICT updates
        statement = statement.on_conflict_do_update(
            index_elements=["repo_full_name", "number"],
            set_=updates,
        ).returning(PR.id)
        
        pr_id = db.execute(statement).scalar_one()
        db.commit()
        return db.get(PR, pr_id)

pr_repository = PRRepository()
