from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class PR(BaseModel):
    """Pull Request model"""
    __tablename__ = "prs"

    github_id = Column(Integer, unique=True, index=True)
    repo_name = Column(String(255), index=True)
    repo_full_name = Column(String(255))
    branch = Column(String(255))
    author = Column(String(255))
    title = Column(String(512))
    status = Column(String(50))  # open, closed, merged
    github_url = Column(String(512))
    diff_url = Column(String(512))
    
    # Relationship to suggestions
    suggestions = relationship("Suggestion", back_populates="pr", cascade="all, delete-orphan")