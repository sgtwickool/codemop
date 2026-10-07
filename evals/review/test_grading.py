"""
Checks of the eval's grading logic, without any API calls:  pytest evals/review/test_grading.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest

from run import Judgement, Verdict, grade, invalid, load_cases, overlaps, same_model

CASES = {c["id"]: c for c in load_cases()}


def comments_on_known_issues(case, offset=0):
    """An oracle: one comment on each known issue, at its first location"""
    return [
        {"id": f"c{n}", "file_path": i["locations"][0]["file"], "line": i["locations"][0]["lines"][0] + offset,
         "end_line": None, "severity": "bug", "title": i["description"][:40], "explanation": "", "suggested_code": None}
        for n, i in enumerate(case["issues"], 1)
    ]


def oracle_judgement(case, comments):
    return Judgement(verdicts=[
        Verdict(comment_id=c["id"], verdict="known_issue", known_issue_id=i["id"], reason="matches")
        for c, i in zip(comments, case["issues"])
    ])


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_the_oracle_passes_every_case(case_id):
    case = CASES[case_id]
    comments = comments_on_known_issues(case)

    scores, meta = grade(case, comments, oracle_judgement(case, comments) if comments else None)

    assert scores["case_pass"] == 1
    assert scores["false_alarms"] == 0
    assert meta["majors_found_ids"] == sorted(i["id"] for i in case["issues"] if i["severity"] == "major")


def test_the_null_review_fails_every_buggy_case_and_passes_every_clean_one():
    """Saying nothing scores 7/25 (the clean cases): the floor every model must beat"""
    results = {case_id: grade(case, [], None)[0]["case_pass"] for case_id, case in CASES.items()}

    assert all(results[c] == 0 for c in CASES if CASES[c]["issues"])
    assert all(results[c] == 1 for c in CASES if not CASES[c]["issues"])
    assert sum(results.values()) == 7


def test_the_right_issue_in_the_wrong_place_isnt_found():
    case = CASES["seeded-pagination"]
    comments = comments_on_known_issues(case, offset=20)

    scores, meta = grade(case, comments, oracle_judgement(case, comments))

    assert scores["case_pass"] == 0
    assert meta["found_in_wrong_place"] == ["major-1"]


def test_within_the_tolerance_is_found():
    case = CASES["seeded-pagination"]
    comments = comments_on_known_issues(case, offset=3)

    assert grade(case, comments, oracle_judgement(case, comments))[0]["case_pass"] == 1


def test_a_false_alarm_fails_a_clean_case():
    case = CASES["clean-docs"]
    comments = [{"id": "c1", "file_path": "docs/deploying.md", "line": 3, "end_line": None}]
    judgement = Judgement(verdicts=[Verdict(comment_id="c1", verdict="false_alarm", reason="style")])

    scores, _ = grade(case, comments, judgement)

    assert (scores["case_pass"], scores["false_alarms"]) == (0, 1)


def test_another_real_issue_on_a_clean_case_isnt_a_false_alarm():
    case = CASES["clean-docs"]
    comments = [{"id": "c1", "file_path": "docs/deploying.md", "line": 3, "end_line": None}]
    judgement = Judgement(verdicts=[Verdict(comment_id="c1", verdict="other_real_issue", reason="real")])

    scores, meta = grade(case, comments, judgement)

    assert scores["case_pass"] == 1
    assert meta["other_real_issues"] == 1


def test_a_missing_verdict_is_a_grader_error_not_a_score():
    case = CASES["seeded-pagination"]
    comments = comments_on_known_issues(case)

    with pytest.raises(RuntimeError, match="no verdict"):
        grade(case, comments, Judgement(verdicts=[]))


def test_a_judgement_naming_no_issue_is_invalid_so_the_judge_is_asked_again():
    case = CASES["real-pr-storage"]
    comments = comments_on_known_issues(case)[:1]
    unnamed = Judgement(verdicts=[Verdict(comment_id="c1", verdict="known_issue", reason="matches")])

    assert "unknown issue None" in invalid(unnamed, case, comments)
    assert "no verdict" in invalid(Judgement(verdicts=[]), case, comments)
    assert invalid(oracle_judgement(case, comments), case, comments) is None


def test_overlap_respects_the_file():
    issue = {"locations": [{"file": "a.py", "lines": [10, 12]}]}

    assert overlaps({"file_path": "a.py", "line": 14}, issue)
    assert not overlaps({"file_path": "b.py", "line": 11}, issue)
    assert not overlaps({"file_path": "a.py", "line": 16}, issue)


def test_a_dated_snapshot_counts_as_the_model_asked_for():
    assert same_model("claude-haiku-4-5-20251001", "claude-haiku-4-5")
    assert same_model("claude-opus-5-5", "claude-opus-5-5")
    assert not same_model("claude-sonnet-5-5", "claude-opus-5-5")
    assert not same_model("claude-haiku-4-5-mini", "claude-haiku-4-5")
