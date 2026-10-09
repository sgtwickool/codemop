from codemop.github.check import blocking, merge_status
from codemop.github.summary import DISMISSED, Finding, SummaryState


def finding(id=1, severity="bug", confidence=0.9, status="open"):
    return Finding(id, severity, "app.py", id, id, f"Issue {id}", "abc", status=status, confidence=confidence)


def test_open_bugs_and_security_issues_at_or_above_the_confidence_block():
    state = SummaryState(findings=[
        finding(1), finding(2, severity="security", confidence=0.8), finding(3, confidence=0.79),
        finding(4, severity="maintainability"), finding(5, severity="performance"), finding(6, status=DISMISSED),
    ])

    assert [f.id for f in blocking(state, 0.8)] == [1, 2]
    assert merge_status(state, 0.8) == (
        "failure", "2 bug or security issues open: fix, or resolve the conversation and comment /codemop check")


def test_one_blocking_issue_reads_naturally():
    assert merge_status(SummaryState(findings=[finding()]), 0.8)[1].startswith("1 bug or security issue open:")
    assert len(merge_status(SummaryState(findings=[finding(i) for i in range(1, 99)]), 0.8)[1]) <= 140


def test_nothing_blocking_passes():
    assert merge_status(SummaryState(findings=[finding(severity="maintainability")]), 0.8) == ("success", "No blocking issues")


def test_a_pr_too_large_to_review_passes_and_says_why():
    state = SummaryState(findings=[finding()])
    assert merge_status(state, 0.8, too_large="9,000 changed lines") == (
        "success", "Not reviewed: over the changed-line limit, so nothing to block on")
