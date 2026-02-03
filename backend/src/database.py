from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://codemop:codemop@localhost:5432/codemop")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class PR(Base):
    __tablename__ = "prs"

    id = Column(Integer, primary_key=True, index=True)
    github_id = Column(Integer, unique=True, index=True)
    repo_name = Column(String(255), index=True)
    repo_full_name = Column(String(255))
    branch = Column(String(255))
    author = Column(String(255))
    title = Column(String(512))
    status = Column(String(50))  # open, closed, merged
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    github_url = Column(String(512))
    diff_url = Column(String(512))

class Suggestion(Base):
    __tablename__ = "suggestions"

    id = Column(Integer, primary_key=True, index=True)
    pr_id = Column(Integer, ForeignKey("prs.id"))
    line_number = Column(Integer)
    file_path = Column(String(512))
    description = Column(Text)
    fix = Column(Text)
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
def init_db():
    Base.metadata.create_all(bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# PR storage functions
def create_pr(db, pr_data: dict):
    """Create a new PR record in the database"""
    db_pr = PR(
        github_id=pr_data.get("github_id"),
        repo_name=pr_data.get("repo_name"),
        repo_full_name=pr_data.get("repo_full_name"),
        branch=pr_data.get("branch"),
        author=pr_data.get("author"),
        title=pr_data.get("title"),
        status=pr_data.get("status"),
        github_url=pr_data.get("github_url"),
        diff_url=pr_data.get("diff_url")
    )
    db.add(db_pr)
    db.commit()
    db.refresh(db_pr)
    return db_pr

def get_pr_by_github_id(db, github_id: int):
    """Get PR by GitHub ID"""
    return db.query(PR).filter(PR.github_id == github_id).first()

def update_pr_status(db, github_id: int, status: str):
    """Update PR status"""
    db_pr = get_pr_by_github_id(db, github_id)
    if db_pr:
        db_pr.status = status
        db.commit()
        db.refresh(db_pr)
    return db_pr

# Suggestion storage functions
def create_suggestion(db, suggestion_data: dict):
    """Create a new suggestion record in the database"""
    db_suggestion = Suggestion(
        pr_id=suggestion_data.get("pr_id"),
        line_number=suggestion_data.get("line_number"),
        file_path=suggestion_data.get("file_path"),
        description=suggestion_data.get("description"),
        fix=suggestion_data.get("fix"),
        confidence=suggestion_data.get("confidence")
    )
    db.add(db_suggestion)
    db.commit()
    db.refresh(db_suggestion)
    return db_suggestion

def get_suggestions_by_pr_id(db, pr_id: int):
    """Get all suggestions for a specific PR"""
    return db.query(Suggestion).filter(Suggestion.pr_id == pr_id).all()

def get_suggestion_by_id(db, suggestion_id: int):
    """Get suggestion by ID"""
    return db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()