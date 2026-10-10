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


# What re-reviews still raise, and what the merge check blocks on
IMPORTANT_SEVERITIES = {Severity.bug, Severity.security}


def location_text(path: str, line: int, end_line: Optional[int] = None) -> str:
    """path:line, or path:line-end for several lines"""
    return f"{path}:{line}" + (f"-{end_line}" if end_line and end_line != line else "")


class OutsideDiff(BaseModel):
    """Where a problem shows up in code outside the diff, shown as context"""
    file_path: str = Field(description="Path of the file, as in the context's #### heading")
    line: int = Field(ge=1, description="Line number where the problem shows up, as numbered in the context")
    end_line: Optional[int] = Field(default=None, ge=1, description="Its last line, if it spans several")


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
    outside_diff: Optional[OutsideDiff] = Field(
        default=None,
        description="Where the problem shows up, when that's in the context rather than the diff, or null",
    )


class ModelReview(BaseModel):
    """A model's review of one chunk of a diff"""
    suggestions: List[ModelSuggestion]
