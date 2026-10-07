from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Text, Float, ForeignKey
from typing import Optional
from app.models.base import BaseModel

class Suggestion(BaseModel):
    """Code suggestion model"""
    __tablename__ = "suggestions"

    pr_id: Mapped[int] = mapped_column(ForeignKey("prs.id"))
    file_path: Mapped[str] = mapped_column(String(512))
    line_number: Mapped[int] = mapped_column()  # first new-file line the suggestion is about
    end_line: Mapped[Optional[int]] = mapped_column()  # last line, if it spans several
    severity: Mapped[Optional[str]] = mapped_column(String(32))  # bug, security, performance, maintainability
    title: Mapped[Optional[str]] = mapped_column(Text)  # one-line summary
    description: Mapped[str] = mapped_column(Text)  # why it's a problem
    fix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # replacement for line_number..end_line
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Relationship to PR
    pr = relationship("PR", back_populates="suggestions")