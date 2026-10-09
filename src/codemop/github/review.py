"""
Turning a review report into what CodeMop posts on a pull request: a review with an inline
comment on each issue (with a one-click ```suggestion block when there's a fix), and one
summary comment in the PR's conversation that each later review edits in place.

The summary records the commit it describes, so a re-run on the same commit can tell it has
already been reviewed. Only a summary by a bot or someone with write access counts: anyone
can comment on a public PR, and a fake summary mustn't be able to stop a review.
"""
import re
from typing import List, Optional, Sequence

from codemop.config import RepoConfig
from codemop.github.client import IssueComment
from codemop.review.pipeline import ReviewReport
from codemop.review.schema import ModelSuggestion, Severity

MARKER = "<!-- codemop-summary -->"
_COMMIT = re.compile(r"<!-- codemop-commit: ([0-9a-f]{7,40}) -->")
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
DEFAULT_MAX_COMMENTS = RepoConfig().max_comments

# Most important first: what goes inline when there are more issues than max_comments
SEVERITY_ORDER = [Severity.security, Severity.bug, Severity.performance, Severity.maintainability]
SEVERITY_LABELS = {
    Severity.security: "🔒 Security",
    Severity.bug: "🐛 Bug",
    Severity.performance: "⚡ Performance",
    Severity.maintainability: "🧹 Maintainability",
}


def ranked(suggestions: Sequence[ModelSuggestion]) -> List[ModelSuggestion]:
    return sorted(suggestions, key=lambda s: (SEVERITY_ORDER.index(s.severity), -s.confidence))


def location(s: ModelSuggestion) -> str:
    return f"{s.file_path}:{s.line}" + (f"-{s.end_line}" if s.end_line and s.end_line != s.line else "")


def comment_body(s: ModelSuggestion) -> str:
    parts = [f"**{SEVERITY_LABELS[s.severity]}: {s.title}**", "", s.explanation]
    if s.suggested_code is not None:
        # A fence longer than any run of backticks in the code, so the code can't end it
        fence = "`" * max(3, max(map(len, re.findall(r"`+", s.suggested_code)), default=0) + 1)
        parts += ["", f"{fence}suggestion", s.suggested_code, fence]
    parts += ["", f"<sub>CodeMop · confidence {s.confidence:.2f}</sub>"]
    return "\n".join(parts)


def inline_comment(s: ModelSuggestion) -> dict:
    comment = {"path": s.file_path, "line": s.end_line or s.line, "side": "RIGHT", "body": comment_body(s)}
    if s.end_line and s.end_line > s.line:
        comment.update(start_line=s.line, start_side="RIGHT")
    return comment


def summary_body(report: ReviewReport, inline: Sequence[ModelSuggestion], not_inline: Sequence[ModelSuggestion],
                 cost: str, head_sha: str, review_url: Optional[str] = None, inline_rejected: bool = False) -> str:
    lines = [MARKER, f"<!-- codemop-commit: {head_sha} -->", f"### CodeMop review of {head_sha[:7]}", ""]
    if report.too_large:
        lines.append(f"Not reviewed: this PR has {report.too_large} set for CodeMop here.")
    elif not report.suggestions:
        lines.append("No issues found." if report.complete else "No issues found in the parts that were reviewed.")
    else:
        where = f" ([comments on the code]({review_url}))" if review_url else ""
        lines += [f"Found {len(report.suggestions)} issue(s){where}:", ""]
        lines += [f"- {SEVERITY_LABELS[s.severity]} `{location(s)}`: {s.title}" for s in inline]
    if not_inline:
        lines += ["", f"Not posted inline (over the limit of {len(inline)} comments; set `max_comments` in `.codemop.yml`):", ""]
        lines += [f"- {SEVERITY_LABELS[s.severity]} `{location(s)}`: {s.title}" for s in not_inline]
    if inline_rejected:
        lines += ["", "⚠️ GitHub didn't accept the comments on the code (has the PR changed since it was "
                      "reviewed?), so the issues are only listed here."]

    if report.failed:
        lines += ["", "⚠️ Some of this PR wasn't reviewed:", ""]
        lines += [f"- {', '.join(f'`{path}`' for path in f.paths)}: {f.reason}" for f in report.failed]

    notes = [f"Skipped `{s.path}`: {s.reason}" for s in report.skipped]
    if report.unplaced:
        notes.append(f"Set aside {len(report.unplaced)} suggestion(s) that pointed at lines outside the diff")
    notes += [f"Left out the suggested fix for `{d.file_path}:{d.line}`: {d.reason}" for d in report.dropped_fixes]
    if notes:
        lines += ["", "<details><summary>Notes</summary>", ""] + [f"- {note}" for note in notes] + ["", "</details>"]

    lines += ["", f"<sub>{report.model} · {report.usage.input_tokens:,} input / "
                  f"{report.usage.output_tokens:,} output tokens · {cost} · this comment is updated "
                  f"when CodeMop reviews new commits</sub>"]
    return "\n".join(lines)


def split_inline(report: ReviewReport, max_comments: int = DEFAULT_MAX_COMMENTS) -> tuple[list, list]:
    """The issues to comment on inline (the most important, up to max_comments), and the rest"""
    issues = ranked(report.suggestions)
    return issues[:max_comments], issues[max_comments:]


def review_payload(inline: Sequence[ModelSuggestion], head_sha: str) -> dict:
    """The body for POST /repos/{owner}/{repo}/pulls/{number}/reviews: the inline comments"""
    return {
        "commit_id": head_sha,
        "event": "COMMENT",  # never approves or requests changes
        "body": f"CodeMop's comments on {head_sha[:7]}; the summary is in the PR's conversation.",
        "comments": [inline_comment(s) for s in inline],
    }


def find_summary(comments: Sequence[IssueComment]) -> Optional[IssueComment]:
    """CodeMop's summary comment on the PR, if there is one by a bot or someone with write access"""
    return next((
        c for c in reversed(comments)
        if MARKER in c.body and (c.author_is_bot or c.author_association in TRUSTED_ASSOCIATIONS)
    ), None)


def reviewed_commit(summary: Optional[IssueComment]) -> Optional[str]:
    """The commit a summary describes"""
    match = _COMMIT.search(summary.body) if summary else None
    return match.group(1) if match else None
