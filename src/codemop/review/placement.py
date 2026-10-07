"""
Checking that each suggestion points at lines GitHub can comment on.

A review comment has to be on an added or unchanged line shown in the diff; a model that
points elsewhere (a removed line, a line outside the hunks, a file it wasn't shown) has
made a mistake, and that suggestion is set aside rather than posted in the wrong place.
"""
from dataclasses import dataclass
from typing import Dict, List, Sequence, Set

from codemop.review.diff import FileDiff
from codemop.review.schema import ModelSuggestion


@dataclass(frozen=True)
class Unplaced:
    suggestion: ModelSuggestion
    reason: str


@dataclass
class Placement:
    placed: List[ModelSuggestion]
    unplaced: List[Unplaced]


def place_suggestions(suggestions: Sequence[ModelSuggestion], files: Sequence[FileDiff]) -> Placement:
    """Split suggestions into those on commentable lines and those that aren't"""
    commentable: Dict[str, Set[int]] = {file.path: file.commentable_lines() for file in files}
    placed: List[ModelSuggestion] = []
    unplaced: List[Unplaced] = []

    for suggestion in suggestions:
        lines = commentable.get(suggestion.file_path)
        end_line = suggestion.end_line or suggestion.line
        if lines is None:
            unplaced.append(Unplaced(suggestion, "file isn't in the reviewed diff"))
        elif end_line < suggestion.line:
            unplaced.append(Unplaced(suggestion, "end_line is before line"))
        elif not set(range(suggestion.line, end_line + 1)) <= lines:
            unplaced.append(Unplaced(suggestion, "lines aren't added or unchanged lines in the diff"))
        else:
            placed.append(suggestion)
    return Placement(placed=placed, unplaced=unplaced)
