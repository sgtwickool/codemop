"""
CodeMop's comments on a pull request's code: one per issue, posted together as a review, with
a one-click ```suggestion block when there's a fix. (The summary in the PR's conversation is
in codemop.github.summary.)
"""
import re
from typing import List, NamedTuple, Optional, Sequence

from codemop.review.schema import ModelSuggestion, Severity, location_text

COMMENT_FOOTER = "<sub>CodeMop · confidence"
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
_FINDING = re.compile(r"<!-- codemop-finding:(\d+) -->")

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
    return location_text(s.file_path, s.line, s.end_line)


def comment_body(s: ModelSuggestion, same_group: Sequence[ModelSuggestion] = (), finding_id: Optional[int] = None) -> str:
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
    if finding_id is not None:  # which of the summary's findings it is
        parts.append(f"<!-- codemop-finding:{finding_id} -->")
    return "\n".join(parts)


def trusted(author_is_bot: bool, author_association: str) -> bool:
    """
    Whether a comment that looks like CodeMop's can be taken as CodeMop's: posted by a bot (the
    workflow's own token) or by someone with write access (a personal access token). Anyone
    can comment on a public PR, including a copy of CodeMop's comments.
    """
    return author_is_bot or author_association in TRUSTED_ASSOCIATIONS


class CodemopComment(NamedTuple):
    severity: Severity
    title: str
    finding_id: Optional[int]  # None for a comment from before they carried it


def codemop_comment(body: str, author_is_bot: bool, author_association: str) -> Optional[CodemopComment]:
    """What one of CodeMop's comments on the code is about, or None if it isn't one of CodeMop's"""
    match = _COMMENT_TITLE.match(body)
    if not match or COMMENT_FOOTER not in body or not trusted(author_is_bot, author_association):
        return None
    severity = next(sev for sev, label in SEVERITY_LABELS.items() if label == match.group(1))
    finding = _FINDING.search(body)
    return CodemopComment(severity, match.group(2), int(finding.group(1)) if finding else None)


def group_of(s: ModelSuggestion, issues: Sequence[ModelSuggestion]) -> List[ModelSuggestion]:
    """The other issues the model grouped with `s` (one problem in several places)"""
    return [other for other in issues if s.group and other is not s and other.group == s.group]


def inline_comment(s: ModelSuggestion, issues: Sequence[ModelSuggestion] = (), finding_id: Optional[int] = None) -> dict:
    comment = {"path": s.file_path, "line": s.end_line or s.line, "side": "RIGHT",
               "body": comment_body(s, group_of(s, issues), finding_id)}
    if s.end_line and s.end_line > s.line:
        comment.update(start_line=s.line, start_side="RIGHT")
    return comment


def review_payload(inline: Sequence[ModelSuggestion], head_sha: str, issues: Sequence[ModelSuggestion] = (),
                   finding_ids: Sequence[int] = ()) -> dict:
    """
    The body for POST /repos/{owner}/{repo}/pulls/{number}/reviews: the inline comments
    (`issues`: all of them; `finding_ids`: the summary's id for each inline one, in order)
    """
    ids = list(finding_ids) or [None] * len(inline)
    return {
        "commit_id": head_sha,
        "event": "COMMENT",  # never approves or requests changes
        "body": f"CodeMop's comments on {head_sha[:7]}; the summary is in the PR's conversation.",
        "comments": [inline_comment(s, issues, finding_id) for s, finding_id in zip(inline, ids)],
    }
