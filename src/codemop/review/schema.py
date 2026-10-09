"""
What a model returns for a review, validated with Pydantic.

Providers ask for this schema using their own structured-output support, then every
response is validated against it here, whichever provider produced it.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    bug = "bug"
    security = "security"
    performance = "performance"
    maintainability = "maintainability"


class ModelSuggestion(BaseModel):
    """One issue, as the model reports it"""
    file_path: str = Field(description="Path of the file, exactly as shown in the diff")
    line: int = Field(ge=1, description="New-file line number (left column) where the issue starts")
    end_line: Optional[int] = Field(
        default=None, ge=1, description="Last line of the issue, if it spans several lines"
    )
    severity: Severity
    title: str = Field(description="One-line summary of the issue")
    explanation: str = Field(description="Why it's a problem, in a sentence or two")
    suggested_code: Optional[str] = Field(
        default=None,
        description="Replacement for lines line..end_line (exact code, no diff markers), or null",
    )
    confidence: float = Field(ge=0, le=1, description="How sure you are this is a real issue")
    group: Optional[str] = Field(
        default=None,
        description="A short label shared by suggestions that fix one problem in several places, or null",
    )


class ModelReview(BaseModel):
    """A model's review of one chunk of a diff"""
    suggestions: List[ModelSuggestion]
