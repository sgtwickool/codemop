from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Text, Float, ForeignKey
from typing import Optional
from app.models.base import BaseModel

class Suggestion(BaseModel):
    """Code suggestion model"""
    __tablename__ = "suggestions"

    pr_id: Mapped[int] = mapped_column(ForeignKey("prs.id"))
    line_number: Mapped[int] = mapped_column()
    file_path: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text)
    fix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Relationship to PR
    pr = relationship("PR", back_populates="suggestions")