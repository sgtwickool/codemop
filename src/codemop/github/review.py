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
_ITEM = re.compile(r"^- \[([ xX])\] (.*) <!-- codemop-fix:([\d,]+) -->$", re.M)
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
COMMENT_FOOTER = "<sub>CodeMop · confidence"
DEFAULT_MAX_COMMENTS = RepoConfig().max_comments

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


def offered_fixes(issues: Sequence[ModelSuggestion], shown: Dict[str, Dict[int, str]]) -> Dict[int, Fix]:
    """The fixes that can be applied later, by the issue's position in `issues` (from 1)"""
    fixes = {}
    for n, s in enumerate(issues, 1):
        end = s.end_line or s.line
        original = [shown.get(s.file_path, {}).get(line) for line in range(s.line, end + 1)]
        if s.suggested_code is not None and None not in original:
            fixes[n] = Fix(n, s.file_path, s.line, end, s.suggested_code, original, s.title)
    return fixes


def _items(numbered: Sequence[Tuple[int, ModelSuggestion]], fixes: Dict[int, Fix],
           checklist: bool) -> List[Tuple[int, str]]:
    """
    A line per issue, and its number, except that issues the model grouped share one line
    (numbered as the first of them), with one checkbox for all their fixes
    """
    lines, listed = [], set()
    for n, s in numbered:
        if n in listed:
            continue
        members = [(m, t) for m, t in numbered if s.group and t.group == s.group] or [(n, s)]
        listed.update(m for m, _ in members)
        ids = [m for m, _ in members if m in fixes]
        if len(members) == 1:
            text = f"{SEVERITY_LABELS[s.severity]} `{location(s)}`: {s.title}"
        else:
            places = ", ".join(f"`{location(t)}`" for _, t in members)
            text = f"{SEVERITY_LABELS[s.severity]} {s.title} ({len(members)} places: {places})"
            if ids and len(ids) < len(members):
                text += f" · fixes for {len(ids)} of them"
        lines.append((n, f"- [ ] {text} <!-- codemop-fix:{','.join(map(str, ids))} -->" if checklist and ids
                      else f"- {text}"))
    return lines


def summary_body(report: ReviewReport, inline: Sequence[ModelSuggestion], not_inline: Sequence[ModelSuggestion],
                 cost: str, head_sha: str, review_url: Optional[str] = None, inline_rejected: bool = False,
                 fixes: Optional[Dict[int, Fix]] = None, checklist: bool = False, teachable: bool = True) -> str:
    """
    With a checklist, issues that have a fix (in `fixes`, numbered by position in inline then
    not_inline) get a checkbox, and the fixes are kept in the comment for `codemop apply`
    """
    fixes = fixes or {}
    checklist = checklist and bool(fixes)
    # A group is listed once, in the section of its first (most important) issue
    items = _items(list(enumerate([*inline, *not_inline], 1)), fixes, checklist)
    lines = [MARKER, f"<!-- codemop-commit: {head_sha} -->", f"### CodeMop review of {head_sha[:7]}", ""]
    if report.too_large:
        lines.append(f"Not reviewed: this PR has {report.too_large} set for CodeMop here.")
    elif not report.suggestions:
        lines.append("No issues found." if report.complete else "No issues found in the parts that were reviewed.")
    else:
        where = f" ([comments on the code]({review_url}))" if review_url else ""
        tick = " Tick the fixes you want, and CodeMop commits them to this branch together." if checklist else ""
        lines += [f"Found {len(report.suggestions)} issue(s){where}.{tick}", ""]
        lines += [line for n, line in items if n <= len(inline)]
    rest = [line for n, line in items if n > len(inline)]
    if rest:
        lines += ["", f"Not posted inline (over the limit of {len(inline)} comments; set `max_comments` in `.codemop.yml`):", ""]
        lines += rest
    if inline_rejected:
        lines += ["", "⚠️ GitHub didn't accept the comments on the code (has the PR changed since it was "
                      "reviewed?), so the issues are only listed here."]

    if report.failed:
        lines += ["", "⚠️ Some of this PR wasn't reviewed:", ""]
        lines += [f"- {', '.join(f'`{path}`' for path in f.paths)}: {f.reason}" for f in report.failed]

    if report.suggestions:
        lines += ["", "<details><summary>How to respond to CodeMop</summary>", ""] + _how_to_respond(checklist, teachable) + [
            "", "</details>"]

    notes = [f"Skipped `{s.path}`: {s.reason}" for s in report.skipped]
    if report.unplaced:
        notes.append(f"Set aside {len(report.unplaced)} suggestion(s) that pointed at lines outside the diff")
    if report.already_dismissed:
        notes.append(f"Left out {report.already_dismissed} suggestion(s) dismissed earlier on this pull request")
    notes += [f"Left out the suggested fix for `{d.file_path}:{d.line}`: {d.reason}" for d in report.dropped_fixes]
    if notes:
        lines += ["", "<details><summary>Notes</summary>", ""] + [f"- {note}" for note in notes] + ["", "</details>"]

    lines += ["", f"<sub>{report.model} · {report.usage.input_tokens:,} input / "
                  f"{report.usage.output_tokens:,} output tokens · {cost} · this comment is updated "
                  f"when CodeMop reviews new commits</sub>"]
    if checklist:
        lines.append(_fixes_data(head_sha, fixes.values(), applied=set()))
    return "\n".join(lines)


def _how_to_respond(checklist: bool, teachable: bool) -> List[str]:
    fix = ("- **Fix it:** tick its box above and CodeMop commits the fix to this branch (ticked fixes are "
           "committed together), or use \"Commit suggestion\" on its comment." if checklist else
           "- **Fix it:** use \"Commit suggestion\" on its comment, where there is one.")
    lines = [fix, "- **Not a problem here:** resolve the comment's conversation. CodeMop won't raise it again on "
                  "this pull request."]
    if teachable:
        lines.append("- **Not a problem anywhere in this repository:** reply `/codemop learn <why it's fine>` to the "
                     "comment. CodeMop adds a note to `.codemop-learned.yml` on this branch, resolves the "
                     "conversation and replies to confirm; once this PR is merged, it won't raise it again in this "
                     "repository. Only people with write access can teach it.")
    else:
        lines.append("- **Not a problem anywhere in this repository:** CodeMop can't commit to a fork's branch, so "
                     "add a note to `.codemop-learned.yml` on the default branch (its header says how).")
    return lines


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
    """The ids of the fixes ticked in the summary's checklist (an item can hold several)"""
    return {int(fix_id) for box, _, ids in _ITEM.findall(_lf(body)) if box.lower() == "x" for fix_id in ids.split(",")}


def record_applied(body: str, commit: str, applied: Sequence[Fix], skipped: Sequence[Tuple[Fix, str]]) -> str:
    """The summary with the applied fixes marked as done in `commit`, and the skipped ones unticked, saying why"""
    done = {f.id for f in applied}
    why = {f.id: reason for f, reason in skipped}

    def item(match: re.Match) -> str:
        ids = [int(i) for i in match.group(3).split(",")]
        marker = f"<!-- codemop-fix:{match.group(3)} -->"
        text = re.sub(r" · (✅|⚠️) .*$", "", match.group(2))  # an earlier result, replaced by this one
        applied_here = [i for i in ids if i in done]
        reasons = [why[i] for i in ids if i in why]
        if applied_here and reasons:
            return f"- [x] {text} · ✅ applied in {commit[:7]}, except {len(reasons)}: {reasons[0]} {marker}"
        if applied_here:
            return f"- [x] {text} · ✅ applied in {commit[:7]} {marker}"
        if reasons:
            return f"- [ ] {text} · ⚠️ not applied: {reasons[0]} {marker}"
        return match.group(0)

    body = _ITEM.sub(item, _lf(body))
    reviewed, fixes, already = stored_fixes(body)
    return _FIXES.sub(lambda _: _fixes_data(reviewed, fixes.values(), already | done), body)


def split_inline(report: ReviewReport, max_comments: int = DEFAULT_MAX_COMMENTS) -> tuple[list, list]:
    """The issues to comment on inline (the most important, up to max_comments), and the rest"""
    issues = ranked(report.suggestions)
    return issues[:max_comments], issues[max_comments:]


def review_payload(inline: Sequence[ModelSuggestion], head_sha: str, issues: Sequence[ModelSuggestion] = ()) -> dict:
    """The body for POST /repos/{owner}/{repo}/pulls/{number}/reviews: the inline comments (`issues`: all of them)"""
    return {
        "commit_id": head_sha,
        "event": "COMMENT",  # never approves or requests changes
        "body": f"CodeMop's comments on {head_sha[:7]}; the summary is in the PR's conversation.",
        "comments": [inline_comment(s, issues) for s in inline],
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
