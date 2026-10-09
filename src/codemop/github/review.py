"""
CodeMop's comments on a pull request's code: one per issue, posted together as a review, with
a one-click ```suggestion block when there's a fix. (The summary in the PR's conversation is
in codemop.github.summary.)
"""
import re
from typing import List, Optional, Sequence, Tuple

from codemop.review.schema import ModelSuggestion, Severity

COMMENT_FOOTER = "<sub>CodeMop · confidence"

# Most important first: what goes inline when there are more issues than max_comments
SEVERITY_ORDER = [Severity.security, Severity.bug, Severity.performance, Severity.maintainability]
SEVERITY_LABELS = {
    Severity.security: "🔒 Security",
    Severity.bug: "🐛 Bug",
    Severity.performance: "⚡ Performance",
    Severity.maintainability: "🧹 Maintainability",
}


_COMMENT_TITLE = re.compile(r"^\*\*(" + "|".join(map(re.escape, SEVERITY_LABELS.values())) + r"): (.+)\*\*$", re.M)


def ranked(suggestions: Sequence[ModelSuggestion]) -> List[ModelSuggestion]:
    return sorted(suggestions, key=lambda s: (SEVERITY_ORDER.index(s.severity), -s.confidence))


def location(s: ModelSuggestion) -> str:
    return f"{s.file_path}:{s.line}" + (f"-{s.end_line}" if s.end_line and s.end_line != s.line else "")


def comment_body(s: ModelSuggestion, same_group: Sequence[ModelSuggestion] = ()) -> str:
    parts = [f"**{SEVERITY_LABELS[s.severity]}: {s.title}**", "", s.explanation]
    if same_group:
        places = ", ".join(f"`{location(other)}`" for other in same_group)
        parts += ["", f"The same problem is also at {places}; the summary has one fix for them all."]
    if s.suggested_code is not None:
        # A fence longer than any run of backticks in the code, so the code can't end it
        fence = "`" * max(3, max(map(len, re.findall(r"`+", s.suggested_code)), default=0) + 1)
        # An empty suggestion deletes the lines; an empty line in the block would replace them with one
        parts += ["", f"{fence}suggestion", *([s.suggested_code] if s.suggested_code else []), fence]
    parts += ["", f"{COMMENT_FOOTER} {s.confidence:.2f} · Not a problem? Resolve this conversation and "
                  "CodeMop won't raise it again on this PR, or reply `/codemop learn <why>` to teach it for the "
                  "whole repository.</sub>"]
    return "\n".join(parts)


def parse_comment(body: str) -> Optional[Tuple[Severity, str]]:
    """The severity and title of one of CodeMop's comments on the code, or None if it isn't one"""
    match = _COMMENT_TITLE.match(body)
    if not match or COMMENT_FOOTER not in body:
        return None
    severity = next(sev for sev, label in SEVERITY_LABELS.items() if label == match.group(1))
    return severity, match.group(2)


def group_of(s: ModelSuggestion, issues: Sequence[ModelSuggestion]) -> List[ModelSuggestion]:
    """The other issues the model grouped with `s` (one problem in several places)"""
    return [other for other in issues if s.group and other is not s and other.group == s.group]


def inline_comment(s: ModelSuggestion, issues: Sequence[ModelSuggestion] = ()) -> dict:
    comment = {"path": s.file_path, "line": s.end_line or s.line, "side": "RIGHT",
               "body": comment_body(s, group_of(s, issues))}
    if s.end_line and s.end_line > s.line:
        comment.update(start_line=s.line, start_side="RIGHT")
    return comment


def review_payload(inline: Sequence[ModelSuggestion], head_sha: str, issues: Sequence[ModelSuggestion] = ()) -> dict:
    """The body for POST /repos/{owner}/{repo}/pulls/{number}/reviews: the inline comments (`issues`: all of them)"""
    return {
        "commit_id": head_sha,
        "event": "COMMENT",  # never approves or requests changes
        "body": f"CodeMop's comments on {head_sha[:7]}; the summary is in the PR's conversation.",
        "comments": [inline_comment(s, issues) for s in inline],
    }
