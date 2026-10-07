from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, String, Text, UniqueConstraint
from typing import List, Optional
from app.models.base import BaseModel

def pr_label(repo_full_name: str, number: int) -> str:
    """How a PR is referred to in logs and messages: owner/repo#123"""
    return f"{repo_full_name}#{number}"

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
    status: Mapped[str] = mapped_column(String(50))  # open, closed or merged
    github_url: Mapped[str] = mapped_column(String(512))
    head_sha: Mapped[Optional[str]] = mapped_column(String(40))  # latest commit on the PR
    analyzed_sha: Mapped[Optional[str]] = mapped_column(String(40))  # commit all its suggestions are for
    
    @property
    def label(self) -> str:
        return pr_label(self.repo_full_name, self.number)
    
    # Relationship to suggestions
    suggestions: Mapped[List["Suggestion"]] = relationship(
        "Suggestion", 
        back_populates="pr", 
        cascade="all, delete-orphan"
    )
