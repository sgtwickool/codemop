"""
Turning a review report into what CodeMop posts on a pull request: a review with an inline
comment on each issue (with a one-click ```suggestion block when there's a fix), and one
summary comment in the PR's conversation that each later review edits in place.

The summary records the commit it describes, so a re-run on the same commit can tell it has
already been reviewed. Only a summary by a bot or someone with write access counts: anyone
can comment on a public PR, and a fake summary mustn't be able to stop a review.

With a checklist, each issue that has a fix gets a checkbox, and the fixes themselves are
kept in the comment (hidden), so ticking some and running `codemop apply` commits them.
"""
import base64
import dataclasses
import json
import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from codemop.config import RepoConfig
from codemop.github.client import IssueComment
from codemop.review.fixes import Fix
from codemop.review.pipeline import ReviewReport
from codemop.review.schema import ModelSuggestion, Severity

MARKER = "<!-- codemop-summary -->"
_COMMIT = re.compile(r"<!-- codemop-commit: ([0-9a-f]{7,40}) -->")
_FIXES = re.compile(r"<!-- codemop-fixes: ([A-Za-z0-9+/=]+) -->")
_ITEM = re.compile(r"^- \[([ xX])\] (.*) <!-- codemop-fix:(\d+) -->$", re.M)
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
        # An empty suggestion deletes the lines; an empty line in the block would replace them with one
        parts += ["", f"{fence}suggestion", *([s.suggested_code] if s.suggested_code else []), fence]
    parts += ["", f"<sub>CodeMop · confidence {s.confidence:.2f}</sub>"]
    return "\n".join(parts)


def inline_comment(s: ModelSuggestion) -> dict:
    comment = {"path": s.file_path, "line": s.end_line or s.line, "side": "RIGHT", "body": comment_body(s)}
    if s.end_line and s.end_line > s.line:
        comment.update(start_line=s.line, start_side="RIGHT")
    return comment


def offered_fixes(issues: Sequence[ModelSuggestion], shown: Dict[str, Dict[int, str]]) -> Dict[int, Fix]:
    """The fixes that can be applied later, by the issue's position in `issues` (from 1)"""
    fixes = {}
    for n, s in enumerate(issues, 1):
        end = s.end_line or s.line
        original = [shown.get(s.file_path, {}).get(line) for line in range(s.line, end + 1)]
        if s.suggested_code is not None and None not in original:
            fixes[n] = Fix(n, s.file_path, s.line, end, s.suggested_code, original, s.title)
    return fixes


def _item(s: ModelSuggestion, fix: Optional[Fix], checklist: bool) -> str:
    text = f"{SEVERITY_LABELS[s.severity]} `{location(s)}`: {s.title}"
    return f"- [ ] {text} <!-- codemop-fix:{fix.id} -->" if checklist and fix else f"- {text}"


def summary_body(report: ReviewReport, inline: Sequence[ModelSuggestion], not_inline: Sequence[ModelSuggestion],
                 cost: str, head_sha: str, review_url: Optional[str] = None, inline_rejected: bool = False,
                 fixes: Optional[Dict[int, Fix]] = None, checklist: bool = False) -> str:
    """
    With a checklist, issues that have a fix (in `fixes`, numbered by position in inline then
    not_inline) get a checkbox, and the fixes are kept in the comment for `codemop apply`
    """
    fixes = fixes or {}
    checklist = checklist and bool(fixes)
    numbered = list(enumerate([*inline, *not_inline], 1))
    lines = [MARKER, f"<!-- codemop-commit: {head_sha} -->", f"### CodeMop review of {head_sha[:7]}", ""]
    if report.too_large:
        lines.append(f"Not reviewed: this PR has {report.too_large} set for CodeMop here.")
    elif not report.suggestions:
        lines.append("No issues found." if report.complete else "No issues found in the parts that were reviewed.")
    else:
        where = f" ([comments on the code]({review_url}))" if review_url else ""
        tick = " Tick the fixes you want, and CodeMop commits them to this branch together." if checklist else ""
        lines += [f"Found {len(report.suggestions)} issue(s){where}.{tick}", ""]
        lines += [_item(s, fixes.get(n), checklist) for n, s in numbered[:len(inline)]]
    if not_inline:
        lines += ["", f"Not posted inline (over the limit of {len(inline)} comments; set `max_comments` in `.codemop.yml`):", ""]
        lines += [_item(s, fixes.get(n), checklist) for n, s in numbered[len(inline):]]
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
    if checklist:
        lines.append(_fixes_data(head_sha, fixes.values(), applied=set()))
    return "\n".join(lines)


def _fixes_data(commit: str, fixes, applied: Set[int]) -> str:
    data = {"commit": commit, "applied": sorted(applied), "fixes": [dataclasses.asdict(f) for f in fixes]}
    # Base64, so nothing in the code can end the HTML comment it's kept in
    return f"<!-- codemop-fixes: {base64.b64encode(json.dumps(data).encode()).decode()} -->"


def stored_fixes(body: str) -> Tuple[Optional[str], Dict[int, Fix], Set[int]]:
    """The commit the summary's fixes were made for, the fixes by id, and the ids already applied"""
    match = _FIXES.search(body)
    if not match:
        return None, {}, set()
    data = json.loads(base64.b64decode(match.group(1)))
    return data["commit"], {f["id"]: Fix(**f) for f in data["fixes"]}, set(data["applied"])


def _lf(body: str) -> str:
    # A comment saved from GitHub's web page (as when a box is ticked there) has \r\n line endings
    return body.replace("\r\n", "\n")


def ticked(body: str) -> Set[int]:
    """The ids of the fixes ticked in the summary's checklist"""
    return {int(fix_id) for box, _, fix_id in _ITEM.findall(_lf(body)) if box.lower() == "x"}


def record_applied(body: str, commit: str, applied: Sequence[Fix], skipped: Sequence[Tuple[Fix, str]]) -> str:
    """The summary with the applied fixes marked as done in `commit`, and the skipped ones unticked, saying why"""
    done = {f.id for f in applied}
    why = {f.id: reason for f, reason in skipped}

    def item(match: re.Match) -> str:
        box, fix_id = match.group(1), int(match.group(3))
        text = re.sub(r" · (✅|⚠️) .*$", "", match.group(2))  # an earlier result, replaced by this one
        if fix_id in done:
            return f"- [x] {text} · ✅ applied in {commit[:7]} <!-- codemop-fix:{fix_id} -->"
        if fix_id in why:
            return f"- [ ] {text} · ⚠️ not applied: {why[fix_id]} <!-- codemop-fix:{fix_id} -->"
        return match.group(0)

    body = _ITEM.sub(item, _lf(body))
    reviewed, fixes, already = stored_fixes(body)
    return _FIXES.sub(lambda _: _fixes_data(reviewed, fixes.values(), already | done), body)


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
