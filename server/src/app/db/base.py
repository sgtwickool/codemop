from typing import Type, TypeVar, Generic, Optional
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType")

# Dialects whose INSERT supports ON CONFLICT (DO NOTHING / DO UPDATE)
_ON_CONFLICT_INSERTS = {
    "postgresql": postgresql.insert,
    "sqlite": sqlite.insert,
}

def on_conflict_insert(db: Session, model):
    """An INSERT for `model` that supports .on_conflict_do_nothing() / .on_conflict_do_update()"""
    dialect = db.get_bind().dialect.name
    if dialect not in _ON_CONFLICT_INSERTS:
        raise NotImplementedError(f"{dialect} is not supported; use PostgreSQL or SQLite")
    return _ON_CONFLICT_INSERTS[dialect](model)

class BaseRepository(Generic[ModelType]):
    """
    Base repository. Repositories never commit: the request (get_db) or the background
    job (session_scope) owns the transaction, so related writes succeed or fail together.
    """
    
    def __init__(self, model: Type[ModelType]):
        self.model = model
    
    def get(self, db: Session, id: int) -> Optional[ModelType]:
        """Get record by ID"""
        return db.get(self.model, id)
