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
    """Base repository with common CRUD operations"""
    
    def __init__(self, model: Type[ModelType]):
        self.model = model
    
    def create(self, db: Session, obj_data: dict) -> ModelType:
        """Create a new record"""
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get(self, db: Session, id: int) -> Optional[ModelType]:
        """Get record by ID"""
        return db.query(self.model).filter(self.model.id == id).first()
    
    def get_by_field(self, db: Session, field_name: str, field_value) -> Optional[ModelType]:
        """Get record by field value"""
        return db.query(self.model).filter(getattr(self.model, field_name) == field_value).first()
    
    def update(self, db: Session, db_obj: ModelType, obj_data: dict) -> ModelType:
        """Update a record"""
        for field, value in obj_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj