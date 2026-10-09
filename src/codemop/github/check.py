"""
The merge check: a "CodeMop" commit status on the PR's latest commit that fails while bugs
or security issues CodeMop is sure enough of are still open, so branch protection can
require it. Off unless a repository's .codemop.yml sets `merge_check: true`.

A commit status rather than the workflow's own result, because workflows that run on
pull_request_target report against the base branch's commit, not the PR's. It's updated on
every review, on CodeMop's own commits, and when someone comments `/codemop check` (GitHub
runs no workflow when a conversation is resolved, so that's how a dismissal reaches it).
"""
from typing import List, Optional, Tuple

from codemop.github.summary import Finding, SummaryState
from codemop.review.schema import Severity

BLOCKING_SEVERITIES = {Severity.bug.value, Severity.security.value}


def blocking(state: SummaryState, confidence: float) -> List[Finding]:
    """The open findings that fail the check: bugs and security issues at least this sure"""
    return [f for f in state.open if f.severity in BLOCKING_SEVERITIES and f.confidence >= confidence]


def merge_status(state: SummaryState, confidence: float, too_large: Optional[str] = None) -> Tuple[str, str]:
    """The status (success or failure) and its description"""
    if too_large:
        return "success", "Not reviewed: over the changed-line limit, so nothing to block on"
    found = blocking(state, confidence)
    if not found:
        return "success", "No blocking issues"
    issues = "1 bug or security issue" if len(found) == 1 else f"{len(found)} bug or security issues"
    return "failure", f"{issues} open: fix, or resolve the conversation and comment /codemop check"
