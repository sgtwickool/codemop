"""
Checking that a suggested fix fits the lines it replaces.

A suggestion block on GitHub replaces lines line..end_line with the suggested code exactly,
so a fix that also repeats the code around those lines (small models often include the line
above or below, or rewrite the whole function) would duplicate that code when applied.
Repeated lines at its edges are trimmed off; a fix that still repeats nearby lines is left
out, and the comment is kept without it.
"""
from typing import Dict, List, Optional, Tuple

from codemop.review.diff import FileDiff
from codemop.review.schema import ModelSuggestion

# Lines shorter than this (")", "else:", "return") can repeat legitimately
DISTINCT_LINE_CHARS = 8


def file_lines(file: FileDiff) -> Dict[int, str]:
    """The new-file lines the diff shows, by number"""
    return {
        line.new_number: line.text
        for hunk in file.hunks
        for line in hunk.lines
        if line.new_number is not None
    }


def _matches(code: List[str], lines: Dict[int, str], first: int) -> bool:
    """Whether `code` is the same as the file's lines from `first` on (all of them shown in the diff)"""
    return all(
        first + i in lines and text.rstrip() == lines[first + i].rstrip()
        for i, text in enumerate(code)
    )


def fit_fix(suggestion: ModelSuggestion, lines: Dict[int, str]) -> Tuple[Optional[str], Optional[str]]:
    """
    The fix to offer for `suggestion`, with any repeated surrounding lines trimmed off, or
    None and the reason it can't be offered. (None and no reason: there was no fix.)
    """
    if suggestion.suggested_code is None:
        return None, None
    start, end = suggestion.line, suggestion.end_line or suggestion.line
    code = suggestion.suggested_code.removesuffix("\n").split("\n")

    # Leading lines that repeat the lines just above, and trailing ones that repeat those just below
    lead = next((n for n in range(len(code), 0, -1) if _matches(code[:n], lines, start - n)), 0)
    code = code[lead:]
    trail = next((n for n in range(len(code), 0, -1) if _matches(code[-n:], lines, end + 1)), 0)
    code = code[:len(code) - trail]
    if not code and (lead or trail):
        return None, "it only repeats the lines around the issue"

    replaced = [lines.get(number) for number in range(start, end + 1)]
    if None not in replaced and [line.rstrip() for line in replaced] == [line.rstrip() for line in code]:
        return None, "it's the same as the current code"

    # Anything still repeating a nearby line (one the fix doesn't replace) would be duplicated
    window = range(start - len(code), end + len(code) + 1)
    nearby = {lines[n].strip() for n in window if n in lines and not start <= n <= end}
    inside = {line.strip() for line in replaced if line is not None}
    for line in code:
        text = line.strip()
        if len(text) >= DISTINCT_LINE_CHARS and text in nearby and text not in inside:
            return None, f"it repeats a nearby line ({text!r}), which applying it would duplicate"
    return "\n".join(code), None
