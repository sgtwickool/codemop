"""
CodeMop's summary comment on a pull request: one comment in the PR's conversation that each
review edits in place.

It keeps every finding from every review of the PR (hidden in the comment, as base64 JSON),
each with a status: open, applied (its fix was ticked and committed), addressed (its code
changed and a later review didn't raise it again) or dismissed (its conversation was
resolved). It's rendered from that each time: the open issues, with a checkbox for each
fix, and the rest under "Done". It also records the commit last reviewed, so a re-run on the
same commit does nothing, and a review of a new commit can look at just what's new.

Only a summary by a bot or someone with write access counts: anyone can comment on a public
PR, and a fake summary mustn't be able to stop a review or change its findings.
"""
import base64
import dataclasses
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from codemop.github.client import IssueComment
from codemop.github.review import SEVERITY_LABELS, ranked
from codemop.review.fixes import Fix, still_there
from codemop.review.pipeline import ReviewReport
from codemop.review.schema import ModelSuggestion, Severity

MARKER = "<!-- codemop-summary -->"
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
_COMMIT = re.compile(r"<!-- codemop-commit: ([0-9a-f]{7,40}) -->")
_STATE = re.compile(r"<!-- codemop-state: ([A-Za-z0-9+/=]+) -->")
_ITEM = re.compile(r"^- \[([ xX])\] (.*) <!-- codemop-fix:([\d,]+) -->$", re.M)

OPEN, APPLIED, ADDRESSED, DISMISSED = "open", "applied", "addressed", "dismissed"


@dataclass
class Finding:
    id: int
    severity: str
    path: str
    line: int
    end_line: int
    title: str
    found_in: str  # the commit whose review found it
    group: Optional[str] = None
    original: Optional[List[str]] = None  # the lines it's about, as reviewed (when the diff showed them)
    code: Optional[str] = None  # its fix, if it has one
    status: str = OPEN
    note: str = ""  # how it was closed, e.g. "applied in abc1234"

    @property
    def fix(self) -> Optional[Fix]:
        if self.code is None or self.original is None:
            return None
        return Fix(self.id, self.path, self.line, self.end_line, self.code, self.original, self.title)

    @property
    def location(self) -> str:
        return f"{self.path}:{self.line}" + (f"-{self.end_line}" if self.end_line != self.line else "")


@dataclass
class SummaryState:
    commit: Optional[str] = None  # the last commit reviewed
    findings: List[Finding] = field(default_factory=list)
    kept: bool = False  # read from a summary that kept its findings (older ones didn't)

    @property
    def open(self) -> List[Finding]:
        return [f for f in self.findings if f.status == OPEN]

    def add(self, suggestions: Sequence[ModelSuggestion], shown: Dict[str, Dict[int, str]], commit: str) -> List[Finding]:
        """New findings for a review's suggestions, most important first; returns them"""
        next_id = max((f.id for f in self.findings), default=0) + 1
        added = []
        for n, s in enumerate(ranked(suggestions)):
            end = s.end_line or s.line
            original = [shown.get(s.file_path, {}).get(line) for line in range(s.line, end + 1)]
            added.append(Finding(
                next_id + n, s.severity.value, s.file_path, s.line, end, s.title, commit, s.group,
                original if None not in original else None, s.suggested_code,
            ))
        self.findings += added
        return added


NEAR_LINES = 3  # a suggestion this close to an earlier finding, same file and severity, is the same issue


def update_earlier(state: SummaryState, new: Sequence[ModelSuggestion], resolved: Set[Tuple[str, str]],
                   head_files: Dict[str, Optional[str]], shown: Dict[str, Dict[int, str]],
                   head: str) -> Tuple[List[ModelSuggestion], List[Finding]]:
    """
    Bring the open findings from earlier reviews up to date with commit `head`:
    - dismissed, if their conversation has been resolved (`resolved`: (path, title) pairs)
    - still open, if this review raised them again (the earlier finding takes the new
      location and fix, rather than being listed twice)
    - addressed, if the lines they were about have gone from the file (`head_files`: path:
      text, None for a deleted file) and this review didn't raise them again
    Returns the suggestions that are new issues, and the findings just addressed. (`shown`: the
    lines the PR's diff shows, by file, for the lines a finding raised again is now about.)
    """
    new = list(new)
    addressed = []
    for f in [f for f in state.open if f.found_in != head]:
        if (f.path, f.title) in resolved:
            f.status, f.note = DISMISSED, "dismissed: its conversation was resolved"
            continue
        again = next((s for s in new if s.file_path == f.path and s.severity.value == f.severity
                      and (abs(s.line - f.line) <= NEAR_LINES or s.title == f.title)), None)
        if again:
            new.remove(again)
            f.line, f.end_line, f.code = again.line, again.end_line or again.line, again.suggested_code
            original = [shown.get(f.path, {}).get(line) for line in range(f.line, f.end_line + 1)]
            f.original = original if None not in original else None
            continue
        if f.original is None:
            continue  # can't tell whether its lines are still there
        text = head_files.get(f.path)
        if text is None or not still_there(text, f.line, f.original):
            f.status, f.note = ADDRESSED, f"addressed in {head[:7]}"
            addressed.append(f)
    return new, addressed


def trusted(author_is_bot: bool, author_association: str) -> bool:
    """
    Whether a comment that looks like CodeMop's can be taken as CodeMop's: posted by a bot (the
    workflow's own token) or by someone with write access (a personal access token)
    """
    return author_is_bot or author_association in TRUSTED_ASSOCIATIONS


def find_summary(comments: Sequence[IssueComment]) -> Optional[IssueComment]:
    """CodeMop's summary comment on the PR, if there is one by a bot or someone with write access"""
    return next((
        c for c in reversed(comments) if MARKER in c.body and trusted(c.author_is_bot, c.author_association)
    ), None)


def read_state(body: Optional[str]) -> SummaryState:
    """The last commit reviewed and the findings kept in a summary (none, for one from before they were kept)"""
    match = _STATE.search(body or "")
    if not match:
        commit = _COMMIT.search(body or "")
        return SummaryState(commit.group(1) if commit else None)
    data = json.loads(base64.b64decode(match.group(1)))
    return SummaryState(data.get("commit"), [Finding(**f) for f in data.get("findings", [])], kept=True)


def _state_data(state: SummaryState) -> str:
    data = {"commit": state.commit, "findings": [dataclasses.asdict(f) for f in state.findings]}
    # Base64, so nothing in the code can end the HTML comment it's kept in
    return f"<!-- codemop-state: {base64.b64encode(json.dumps(data).encode()).decode()} -->"


def _label(f: Finding) -> str:
    return SEVERITY_LABELS[Severity(f.severity)]


def _open_items(findings: Sequence[Finding], checklist: bool, new_in: Optional[str]) -> List[str]:
    """
    A line per open finding, except that findings the model grouped share one line, with one
    checkbox for all their fixes
    """
    lines, listed = [], set()
    for f in findings:
        if f.id in listed:
            continue
        members = [m for m in findings if f.group and m.group == f.group] or [f]
        listed.update(m.id for m in members)
        ids = [m.id for m in members if m.fix]
        if len(members) == 1:
            text = f"{_label(f)} `{f.location}`: {f.title}"
        else:
            text = f"{_label(f)} {f.title} ({len(members)} places: {', '.join(f'`{m.location}`' for m in members)})"
            if ids and len(ids) < len(members):
                text += f" · fixes for {len(ids)} of them"
        if new_in and all(m.found_in == new_in for m in members):
            text += " · new"
        lines.append(f"- [ ] {text} <!-- codemop-fix:{','.join(map(str, ids))} -->" if checklist and ids
                     else f"- {text}")
    return lines


def _done_items(findings: Sequence[Finding]) -> List[str]:
    icons = {APPLIED: "✅", ADDRESSED: "✅", DISMISSED: "➖"}
    return [f"- {icons[f.status]} {_label(f)} `{f.location}`: {f.title} · {f.note}" for f in findings]


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


def summary_body(state: SummaryState, report: ReviewReport, cost: str, *, review_url: Optional[str] = None,
                 inline_rejected: bool = False, checklist: bool = False, teachable: bool = True,
                 since: Optional[str] = None, less_important: int = 0, not_commented: int = 0) -> str:
    """
    The summary for `state` (whose commit is the one just reviewed), with what this review
    (`report`) found. `since`: the commit a re-review looked at the changes after
    """
    head = state.commit or ""
    checklist = checklist and any(f.fix for f in state.open)
    lines = [MARKER, f"<!-- codemop-commit: {head} -->", f"### CodeMop review of {head[:7]}", ""]
    if since:
        lines += [f"Reviewed the changes since {since[:7]}.", ""]
    if report.too_large:
        lines += [f"Not reviewed: this PR has {report.too_large} set for CodeMop here.", ""]

    new = [f for f in state.findings if f.found_in == head]
    if state.open:
        where = f" ([comments on the code]({review_url}))" if review_url and new else ""
        tick = " Tick the fixes you want, and CodeMop commits them to this branch together." if checklist else ""
        lines += [f"{len(state.open)} open issue(s){where}.{tick}", ""]
        lines += _open_items(state.open, checklist, head if since else None)
    elif not report.too_large:
        reviewed = "the parts that were reviewed" if not report.complete else ("these changes" if since else "")
        lines.append(f"No issues found in {reviewed}." if reviewed else "No issues found.")
    if inline_rejected:
        lines += ["", "⚠️ GitHub didn't accept the comments on the code (has the PR changed since it was "
                      "reviewed?), so the issues are only listed here."]

    if report.failed:
        lines += ["", "⚠️ Some of this PR wasn't reviewed:", ""]
        lines += [f"- {', '.join(f'`{path}`' for path in f.paths)}: {f.reason}" for f in report.failed]

    done = [f for f in state.findings if f.status != OPEN]
    if done:
        lines += ["", f"<details><summary>Done ({len(done)})</summary>", ""] + _done_items(done) + ["", "</details>"]
    if state.open:
        lines += ["", "<details><summary>How to respond to CodeMop</summary>", ""]
        lines += _how_to_respond(checklist, teachable) + ["", "</details>"]

    notes = [f"Skipped `{s.path}`: {s.reason}" for s in report.skipped]
    if report.unplaced:
        notes.append(f"Set aside {len(report.unplaced)} suggestion(s) that pointed at lines outside the diff")
    if report.already_dismissed:
        notes.append(f"Left out {report.already_dismissed} suggestion(s) dismissed earlier on this pull request")
    if less_important:
        notes.append(f"Left out {less_important} less important suggestion(s): re-reviews only raise bugs and "
                     "security issues")
    if not_commented:
        notes.append(f"{not_commented} issue(s) are listed here without a comment on the code (over the "
                     "`max_comments` limit set in `.codemop.yml`)")
    notes += [f"Left out the suggested fix for `{d.file_path}:{d.line}`: {d.reason}" for d in report.dropped_fixes]
    if notes:
        lines += ["", "<details><summary>Notes</summary>", ""] + [f"- {note}" for note in notes] + ["", "</details>"]

    lines += ["", f"<sub>{report.model} · {report.usage.input_tokens:,} input / "
                  f"{report.usage.output_tokens:,} output tokens · {cost} · this comment is updated "
                  f"when CodeMop reviews new commits</sub>", _state_data(state)]
    return "\n".join(lines)


def _lf(body: str) -> str:
    # A comment saved from GitHub's web page (as when a box is ticked there) has \r\n line endings
    return body.replace("\r\n", "\n")


def ticked(body: str) -> Set[int]:
    """The ids of the findings whose fixes are ticked in the summary's checklist"""
    return {int(i) for box, _, ids in _ITEM.findall(_lf(body)) if box.lower() == "x" for i in ids.split(",")}


def record_applied(body: str, commit: str, applied: Sequence[Fix], skipped: Sequence[Tuple[Fix, str]]) -> str:
    """
    The summary with the applied fixes marked as done in `commit` (in its checklist now, and
    in its findings, so the next review lists them under Done), and the skipped ones
    unticked, saying why
    """
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
    state = read_state(body)
    for f in state.findings:
        if f.id in done:
            f.status, f.note = APPLIED, f"applied in {commit[:7]}"
    return _STATE.sub(lambda _: _state_data(state), body)


def stored_fixes(body: str) -> Dict[int, Fix]:
    """The fixes of the summary's open findings, by id"""
    return {f.id: f.fix for f in read_state(body).open if f.fix}
