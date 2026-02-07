from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String
from typing import List
from app.models.base import BaseModel

class PR(BaseModel):
    """Pull Request model"""
    __tablename__ = "prs"

    github_id: Mapped[int] = mapped_column(unique=True, index=True)
    repo_name: Mapped[str] = mapped_column(String(255), index=True)
    repo_full_name: Mapped[str] = mapped_column(String(255))
    branch: Mapped[str] = mapped_column(String(255))
    author: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(50))  # open, closed, merged
    github_url: Mapped[str] = mapped_column(String(512))
    diff_url: Mapped[str] = mapped_column(String(512))
    
    # Relationship to suggestions
    suggestions: Mapped[List["Suggestion"]] = relationship(
        "Suggestion", 
        back_populates="pr", 
        cascade="all, delete-orphan"
    )