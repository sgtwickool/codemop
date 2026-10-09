"""
The checklist in CodeMop's summary: a checkbox for each fix, which only selects it, and a
"Commit the ticked fixes" box, which commits everything ticked as one commit. These read and
edit the summary's text (with \n line endings: see conversation.list_issue_comments).
"""
import re
from typing import Dict, Optional, Sequence, Set, Tuple

from codemop.github.summary import APPLIED, COMMIT_BOX, COMMIT_BOX_TEXT, fix_marker, read_state, write_state
from codemop.review.fixes import Fix

_ITEM = re.compile(r"^- \[([ xX])\] (.*) <!-- codemop-fix:([\d,]+) -->$", re.M)
_COMMIT_BOX = re.compile(r"^- \[([ xX])\] " + re.escape(COMMIT_BOX_TEXT) + "$", re.M)


def ticked(body: str) -> Set[int]:
    """The ids of the findings whose fixes are ticked"""
    return {int(i) for box, _, ids in _ITEM.findall(body) if box.lower() == "x" for i in ids.split(",")}


def commit_requested(body: str) -> bool:
    """Whether "Commit the ticked fixes" is ticked"""
    match = _COMMIT_BOX.search(body)
    return bool(match) and match.group(1).lower() == "x"


def untick_commit(body: str) -> str:
    """The summary with "Commit the ticked fixes" unticked, ready for next time"""
    return _COMMIT_BOX.sub(COMMIT_BOX, body)


def stored_fixes(body: str) -> Dict[int, Fix]:
    """The fixes of the summary's open findings, by id"""
    return {f.id: f.fix for f in read_state(body).open if f.fix}


def record_applied(body: str, commit: str, applied: Sequence[Fix], skipped: Sequence[Tuple[Fix, str]]) -> str:
    """
    The summary with the applied fixes marked as done in `commit` (in its checklist now, and
    in its findings, so the next review lists them under Done), the skipped ones unticked,
    saying why, and "Commit the ticked fixes" unticked
    """
    done = {f.id for f in applied}
    why = {f.id: reason for f, reason in skipped}

    def item(match: re.Match) -> str:
        ids = [int(i) for i in match.group(3).split(",")]
        marker = fix_marker(ids)
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

    body = untick_commit(_ITEM.sub(item, body))
    state = read_state(body)
    for f in state.findings:
        if f.id in done:
            f.status, f.note = APPLIED, f"applied in {commit[:7]}"
    return write_state(body, state)


def record_own_commit(body: str, parent: str, commit: str) -> Optional[str]:
    """
    The summary with CodeMop's own commit (ticked fixes, a learned note) recorded as reviewed,
    if it was made on top of the commit last reviewed: it holds nothing CodeMop hasn't seen,
    so the merge check can be set on it, and the next re-review skips it. None otherwise (if
    someone pushed in between, that push gets its own review).
    """
    state = read_state(body)
    if state.commit is None or state.commit != parent:
        return None
    state.commit = commit
    return write_state(body, state)
