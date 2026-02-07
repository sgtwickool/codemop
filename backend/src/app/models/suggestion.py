from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class Suggestion(BaseModel):
    """Code suggestion model"""
    __tablename__ = "suggestions"

    pr_id = Column(Integer, ForeignKey("prs.id"))
    line_number = Column(Integer)
    file_path = Column(String(512))
    description = Column(Text)
    fix = Column(Text)
    confidence = Column(Float)
    
    # Relationship to PR
    pr = relationship("PR", back_populates="suggestions")