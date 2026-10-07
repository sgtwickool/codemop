from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, String, Text, UniqueConstraint
from typing import List
from app.models.base import BaseModel

class PR(BaseModel):
    """Pull Request model"""
    __tablename__ = "prs"
    # PR numbers restart at 1 in every repository, so a PR is identified by both
    __table_args__ = (
        UniqueConstraint("repo_full_name", "number", name="uq_prs_repo_full_name_number"),
    )

    number: Mapped[int] = mapped_column(BigInteger)  # the PR number shown on GitHub (#123)
    repo_name: Mapped[str] = mapped_column(String(255), index=True)
    repo_full_name: Mapped[str] = mapped_column(String(255))
    branch: Mapped[str] = mapped_column(String(255))
    author: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50))  # open, closed, merged
    github_url: Mapped[str] = mapped_column(String(512))
    diff_url: Mapped[str] = mapped_column(String(512))
    
    # Relationship to suggestions
    suggestions: Mapped[List["Suggestion"]] = relationship(
        "Suggestion", 
        back_populates="pr", 
        cascade="all, delete-orphan"
    )
