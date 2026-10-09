"""The merge check, and codemop check."""


from codemop.github.api import ReviewThread
from codemop.github.summary import read_state
from codemop.providers.base import NoReview
from codemop.review.schema import Severity
from cli_support import (  # noqa: F401
    DIFF, SUGGESTION, FakeModel, run, RecordingModel, TWO_FILE_DIFF, summary_of, tick_all, _async, codemop_comment, learn_reply, posted_with_a_personal_token, new_commit, NEWER, merge_check_on,
)


def test_no_merge_check_unless_the_repository_turns_it_on(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert github["statuses"] == []


def test_the_merge_check_is_pending_during_a_review_then_fails_on_a_bug(capsys, monkeypatch, fake_model, github):
    merge_check_on(github)
    fake_model([SUGGESTION])

    code, _, _ = run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert code == 0  # the review worked: the check is what fails
    head = github["head"]
    assert github["statuses"] == [
        (head, "pending", "Reviewing the latest changes", None),
        (head, "failure", "1 bug or security issue open: fix, or resolve the conversation and comment /codemop check",
         "https://github.com/owner/repo/pull/7#issuecomment-100"),
    ]
    assert "**The merge check** (the \"CodeMop\" status) fails while bugs or security issues are open" in summary_of(github)


def test_the_merge_check_passes_without_blocking_issues(capsys, monkeypatch, fake_model, github):
    merge_check_on(github)
    fake_model([SUGGESTION.model_copy(update={"severity": Severity.maintainability})])

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert github["statuses"][-1][1:3] == ("success", "No blocking issues")


def test_the_merge_check_confidence_is_the_repositorys(capsys, monkeypatch, fake_model, github):
    github["default_branch"][".codemop.yml"] = "merge_check: true\nmerge_check_confidence: 0.95\n"
    fake_model([SUGGESTION])  # 0.9 sure

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert github["statuses"][-1][1] == "success"


def test_the_merge_check_is_an_error_when_the_review_couldnt_be_done(capsys, monkeypatch, fake_model, github):
    merge_check_on(github)
    fake_model(NoReview("Anthropic rejected the API key: check ANTHROPIC_API_KEY", fatal=True))

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert github["statuses"][-1][1:3] == ("error", "Couldn't review: Anthropic rejected the API key: check ANTHROPIC_API_KEY")


def test_resolving_the_conversation_passes_the_check(capsys, monkeypatch, fake_model, github):
    merge_check_on(github)
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])
    codemop_comment(github)
    github["threads"][0] = ReviewThread(**{**github["threads"][0].__dict__, "resolved": True})

    code, _, _ = run(capsys, monkeypatch, ["check", "owner/repo#7", "--comment", "321"])

    assert code == 0
    assert github["statuses"][-1][:3] == (github["head"], "success", "No blocking issues")
    assert github["reactions"] == [(321, "+1")]  # so whoever asked knows it ran


def test_a_ticked_fix_commit_gets_the_check_too(capsys, monkeypatch, fake_model, github):
    """No review runs on CodeMop's own commit, so without this a required check would wait forever"""
    merge_check_on(github)
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    tick_all(github)

    run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])

    assert github["statuses"][-1][:3] == ("c0ffee0" + "0" * 33, "success", "No blocking issues")


def test_check_does_nothing_before_the_first_review_or_when_its_off(capsys, monkeypatch, github):
    merge_check_on(github)
    assert run(capsys, monkeypatch, ["check", "owner/repo#7"])[0] == 0
    github["default_branch"].clear()
    assert run(capsys, monkeypatch, ["check", "owner/repo#7"])[0] == 0
    assert github["statuses"] == []


def test_check_wont_pass_a_commit_that_hasnt_been_reviewed(capsys, monkeypatch, fake_model, github):
    """Found by CodeMop on PR #14: after a push, /codemop check could set success on unreviewed code"""
    merge_check_on(github)
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])
    codemop_comment(github)
    github["threads"][0] = ReviewThread(**{**github["threads"][0].__dict__, "resolved": True})
    new_commit(github)  # pushed, not reviewed yet
    before = list(github["statuses"])

    code, _, _ = run(capsys, monkeypatch, ["check", "owner/repo#7", "--comment", "321"])

    assert code == 0
    assert github["statuses"] == before
    assert github["reactions"] == []
    assert any("The latest commit hasn't been reviewed yet" in body for body, _, _ in github["comments"].values())


def test_codemops_own_commit_counts_as_reviewed(capsys, monkeypatch, fake_model, github):
    merge_check_on(github)
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    tick_all(github)
    run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])

    assert read_state(summary_of(github)).commit == github["head"]  # the fix commit
    code, _, _ = run(capsys, monkeypatch, ["check", "owner/repo#7"])
    assert code == 0 and github["statuses"][-1][0] == github["head"]


def test_a_fix_committed_on_top_of_someone_elses_push_isnt_counted_as_reviewed(capsys, monkeypatch, fake_model, github):
    merge_check_on(github)
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    reviewed = github["head"]
    tick_all(github)
    github["branch_moves"] = 1  # someone pushes while the fix is being committed
    statuses = len(github["statuses"])

    run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])

    assert read_state(summary_of(github)).commit == reviewed  # their push gets its own review
    assert len(github["statuses"]) == statuses  # and nothing is set on unreviewed code
