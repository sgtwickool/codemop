"""
CodeMop's summary comment on a pull request: one comment in the PR's conversation that each
review edits in place.

It keeps every finding from every review of the PR (hidden in the comment, as base64 JSON),
each with a status: open, applied (its fix was ticked and committed), addressed (its code
changed and a later review didn't raise it again) or dismissed (its conversation was
resolved). It's rendered from that each time: the open issues, with a checkbox for each
fix (see checklist.py), and the rest under "Done". It also records the commit last
reviewed, so a re-run on the same commit does nothing, and a review of a new commit can look
at just what's new.

Only a summary by a bot or someone with write access counts: anyone can comment on a public
PR, and a fake summary mustn't be able to stop a review or change its findings.
"""
import base64
import dataclasses
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from codemop.config import CONFIG_FILE
from codemop.github.conversation import IssueComment
from codemop.github.review import SEVERITY_LABELS, ranked, trusted
from codemop.review.fixes import Fix, lines_between, still_there
from codemop.review.learned import LEARNED_FILE, same_issue
from codemop.review.pipeline import ReviewReport
from codemop.review.schema import ModelSuggestion, Severity, location_text

MARKER = "<!-- codemop-summary -->"
MAX_COMMENT_CHARS = 65_000  # GitHub's limit is 65,536
_STATE = re.compile(r"<!-- codemop-state: ([A-Za-z0-9+/=]+) -->")
# Ticking fixes only selects them; ticking this commits them, so several go in one commit
COMMIT_BOX_TEXT = "**Commit the ticked fixes** <!-- codemop-commit-ticked -->"
COMMIT_BOX = f"- [ ] {COMMIT_BOX_TEXT}"

OPEN, APPLIED, ADDRESSED, DISMISSED = "open", "applied", "addressed", "dismissed"


def fix_marker(ids: Sequence[int]) -> str:
    """What ties a checklist item to its findings"""
    return f"<!-- codemop-fix:{','.join(map(str, ids))} -->"


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
    confidence: float = 0.0  # how sure the model was
    # Where it shows up outside the diff, if it does (a caller the change breaks): path, line,
    # end_line, and original, those lines as reviewed. Changing them can address it too
    outside: Optional[dict] = None

    @property
    def fix(self) -> Optional[Fix]:
        if self.code is None or self.original is None:
            return None
        return Fix(self.id, self.path, self.line, self.end_line, self.code, self.original, self.title)

    @property
    def location(self) -> str:
        return location_text(self.path, self.line, self.end_line)


@dataclass
class SummaryState:
    commit: Optional[str] = None  # the last commit reviewed (None: no summary yet)
    findings: List[Finding] = field(default_factory=list)

    @property
    def open(self) -> List[Finding]:
        return [f for f in self.findings if f.status == OPEN]

    def add(self, suggestions: Sequence[ModelSuggestion], shown: Dict[str, Dict[int, str]], commit: str,
            files: Mapping[str, Optional[str]] = {}) -> List[Finding]:
        """
        New findings for a review's suggestions, most important first (so ids are in that
        order); returns them. (`files`: the text at `commit` of the files they show up in
        outside the diff, for the lines they're about there.)
        """
        next_id = max((f.id for f in self.findings), default=0) + 1
        added = [
            Finding(next_id + n, s.severity.value, s.file_path, s.line, s.end_line or s.line, s.title, commit, s.group,
                    lines_between(shown.get(s.file_path, {}), s.line, s.end_line or s.line), s.suggested_code,
                    confidence=s.confidence, outside=outside_of(s, files))
            for n, s in enumerate(ranked(suggestions))
        ]
        self.findings += added
        return added


def outside_of(s: ModelSuggestion, files: Mapping[str, Optional[str]]) -> Optional[dict]:
    """Where a suggestion shows up outside the diff, with those lines from the file, if it says"""
    if s.outside_diff is None:
        return None
    place = s.outside_diff
    end_line = place.end_line or place.line
    text = files.get(place.file_path)
    lines = text.splitlines() if text is not None else []
    original = lines[place.line - 1:end_line] if text is not None and end_line <= len(lines) else None
    return {"path": place.file_path, "line": place.line, "end_line": end_line, "original": original}


def sync_threads(state: SummaryState, threads: Sequence[Tuple[Optional[int], str, str, bool]]) -> None:
    """
    Match findings to their conversations ((finding id, path, title, resolved) for each of
    CodeMop's threads; by id, or by path and title for a comment from before ids were in
    them): resolved dismisses an open finding, and unresolving reopens a dismissed one
    """
    for finding_id, path, title, resolved in threads:
        for f in state.findings:
            if (f.id != finding_id) if finding_id is not None else ((f.path, f.title) != (path, title)):
                continue
            if resolved and f.status == OPEN:
                f.status, f.note = DISMISSED, "dismissed: its conversation was resolved"
            elif not resolved and f.status == DISMISSED:
                f.status, f.note = OPEN, ""


def update_earlier(state: SummaryState, new: Sequence[ModelSuggestion], head_files: Dict[str, Optional[str]],
                   shown: Dict[str, Dict[int, str]], head: str) -> Tuple[List[ModelSuggestion], List[Finding]]:
    """
    Bring the open findings from earlier reviews up to date with commit `head` (after
    sync_threads has dismissed the ones whose conversations were resolved):
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
        again = next((s for s in new if same_issue(s, f.path, f.line, Severity(f.severity), f.title)), None)
        if again:
            new.remove(again)
            f.line, f.end_line, f.code = again.line, again.end_line or again.line, again.suggested_code
            f.original = lines_between(shown.get(f.path, {}), f.line, f.end_line)
            f.outside = outside_of(again, head_files)
            continue
        # Its lines in the diff, and where it shows up outside it: changing either can address it
        # (whichever we can tell about: lines we have, in a file that's changed since)
        places = [(f.path, f.line, f.original)]
        if f.outside:
            places.append((f.outside["path"], f.outside["line"], f.outside["original"]))
        known = [(path, line, original) for path, line, original in places if original is not None and path in head_files]
        if any(head_files[path] is None or not still_there(head_files[path], line, original)
               for path, line, original in known):
            f.status, f.note = ADDRESSED, f"addressed in {head[:7]}"
            addressed.append(f)
    return new, addressed


def find_summary(comments: Sequence[IssueComment]) -> Optional[IssueComment]:
    """CodeMop's summary comment on the PR, if there is one by a bot or someone with write access"""
    return next((
        c for c in reversed(comments) if MARKER in c.body and trusted(c.author_is_bot, c.author_association)
    ), None)


def read_state(body: Optional[str]) -> SummaryState:
    """The last commit reviewed and the findings kept in a summary"""
    match = _STATE.search(body or "")
    if not match:
        return SummaryState()
    data = json.loads(base64.b64decode(match.group(1)))
    return SummaryState(data.get("commit"), [Finding(**f) for f in data.get("findings", [])])


def _state_data(state: SummaryState) -> str:
    findings = []
    for f in state.findings:
        data = dataclasses.asdict(f)
        if f.status != OPEN:  # done: its fix and lines aren't needed any more
            data.update(code=None, original=None)
            if f.outside:
                data["outside"] = {**f.outside, "original": None}
        findings.append(data)
    # Base64, so nothing in the code can end the HTML comment it's kept in
    data = {"commit": state.commit, "findings": findings}
    return f"<!-- codemop-state: {base64.b64encode(json.dumps(data).encode()).decode()} -->"


def write_state(body: str, state: SummaryState) -> str:
    """The summary with `state` kept in it in place of what was there"""
    return _STATE.sub(lambda _: _state_data(state), body)


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
        lines.append(f"- [ ] {text} {fix_marker(ids)}" if checklist and ids else f"- {text}")
    return lines


def _done_items(findings: Sequence[Finding]) -> List[str]:
    icons = {APPLIED: "✅", ADDRESSED: "✅", DISMISSED: "➖"}
    return [f"- {icons[f.status]} {_label(f)} `{f.location}`: {f.title} · {f.note}" for f in findings]


def _how_to_respond(checklist: bool, teachable: bool, merge_check: bool) -> List[str]:
    fix = ("- **Fix it:** tick its box above, and when you've ticked all you want, tick **Commit the ticked "
           "fixes**: CodeMop commits them to this branch as one commit. Or use \"Commit suggestion\" on its "
           "comment." if checklist else
           "- **Fix it:** use \"Commit suggestion\" on its comment, where there is one.")
    lines = [fix, "- **Not a problem here:** resolve the comment's conversation. CodeMop won't raise it again on "
                  "this pull request."]
    if teachable:
        lines.append("- **Not a problem anywhere in this repository:** reply `/codemop learn <why it's fine>` to the "
                     f"comment. CodeMop adds a note to `{LEARNED_FILE}` on this branch, resolves the "
                     "conversation and replies to confirm; once this PR is merged, it won't raise it again in this "
                     "repository. Only people with write access can teach it.")
    else:
        lines.append("- **Not a problem anywhere in this repository:** CodeMop can't commit to a fork's branch, so "
                     f"add a note to `{LEARNED_FILE}` on the default branch (its header says how).")
    if merge_check:
        lines.append("- **The merge check** (the \"CodeMop\" status) fails while bugs or security issues are open. "
                     "It's updated on every push; after resolving a conversation, comment `/codemop check` to "
                     "update it straight away.")
    return lines


def summary_body(state: SummaryState, report: ReviewReport, cost: str, **options) -> str:
    """
    The summary for `state` (whose commit is the one just reviewed), with what this review
    (`report`) found, within GitHub's size limit: if the fixes kept in it make it too long,
    the open findings give up their fixes (their checkboxes), and only then their lines (which
    tell later reviews whether they've been addressed). Options as for _summary_body.
    """
    body = _summary_body(state, report, cost, **options)
    for drop in ("code", "original"):
        if len(body) <= MAX_COMMENT_CHARS:
            break
        for finding in state.open:
            setattr(finding, drop, None)
        body = _summary_body(state, report, cost, **options)
    return body


def _summary_body(state: SummaryState, report: ReviewReport, cost: str, *, review_url: Optional[str] = None,
                  inline_rejected: bool = False, checklist: bool = False, teachable: bool = True,
                  since: Optional[str] = None, less_important: int = 0, not_commented: int = 0,
                  merge_check: bool = False) -> str:
    """`since`: the commit a re-review looked at the changes after"""
    head = state.commit or ""
    checklist = checklist and any(f.fix for f in state.open)
    lines = [MARKER, f"### CodeMop review of {head[:7]}", ""]
    if since:
        lines += [f"Reviewed the changes since {since[:7]}.", ""]
    if report.too_large:
        lines += [f"Not reviewed: this PR has {report.too_large} set for CodeMop here.", ""]

    new = [f for f in state.findings if f.found_in == head]
    if state.open:
        where = f" ([comments on the code]({review_url}))" if review_url and new else ""
        tick = (" Tick the fixes you want, then tick **Commit the ticked fixes** at the end, and CodeMop commits them "
                "to this branch as one commit." if checklist else "")
        lines += [f"{len(state.open)} open issue(s){where}.{tick}", ""]
        lines += _open_items(state.open, checklist, head if since else None)
        if checklist:
            lines += ["", COMMIT_BOX]
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
        lines += _how_to_respond(checklist, teachable, merge_check) + ["", "</details>"]

    notes = report.notes(code=lambda text: f"`{text}`")
    if less_important:
        notes.append(f"Left out {less_important} less important suggestion(s): re-reviews only raise bugs and "
                     "security issues")
    if not_commented:
        notes.append(f"{not_commented} issue(s) are listed here without a comment on the code (over the "
                     f"`max_comments` limit set in `{CONFIG_FILE}`)")
    if notes:
        lines += ["", "<details><summary>Notes</summary>", ""] + [f"- {note}" for note in notes] + ["", "</details>"]

    lines += ["", f"<sub>{report.model} · {report.usage.input_tokens:,} input / "
                  f"{report.usage.output_tokens:,} output tokens · {cost} · this comment is updated "
                  f"when CodeMop reviews new commits</sub>", _state_data(state)]
    return "\n".join(lines)
