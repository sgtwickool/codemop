from codemop.github.client import IssueComment
from codemop.github.review import (
    MARKER, comment_body, find_summary, review_payload, reviewed_commit, split_inline, summary_body,
)
from codemop.providers.base import Usage
from codemop.review.chunks import Skipped
from codemop.review.pipeline import DroppedFix, FailedChunk, ReviewReport
from codemop.review.schema import ModelSuggestion

SHA = "abc1234" + "0" * 33


def suggestion(line=3, end_line=None, severity="bug", confidence=0.9, title="Adds one to the total", code="    return result"):
    return ModelSuggestion(file_path="app.py", line=line, end_line=end_line, severity=severity, title=title,
                           explanation="The +1 looks accidental.", suggested_code=code, confidence=confidence)


def report(*suggestions, **fields):
    return ReviewReport(model="anthropic/claude-opus-5-5", suggestions=list(suggestions),
                        usage=Usage(input_tokens=2000, output_tokens=300), chunks=1, **fields)


def test_a_comment_with_a_fix_has_a_suggestion_block():
    assert comment_body(suggestion()) == (
        "**🐛 Bug: Adds one to the total**\n\nThe +1 looks accidental.\n\n"
        "```suggestion\n    return result\n```\n\n<sub>CodeMop · confidence 0.90</sub>"
    )


def test_a_comment_without_a_fix_has_no_suggestion_block():
    assert "suggestion" not in comment_body(suggestion(code=None)).split("<sub>")[0]


def test_backticks_in_the_fix_get_a_longer_fence():
    body = comment_body(suggestion(code='doc = """\n```python\nx\n```\n"""'))
    assert "````suggestion\n" in body and body.count("````") == 2


def summary(r, max_comments=10, **kwargs):
    inline, rest = split_inline(r, max_comments)
    return summary_body(r, inline, rest, "about $0.02", SHA, **kwargs)


def test_inline_comments_point_at_the_lines_on_the_new_side():
    payload = review_payload([suggestion(line=3), suggestion(line=5, end_line=7)], SHA)

    single, multi = payload["comments"]
    assert (single["path"], single["line"], single["side"]) == ("app.py", 3, "RIGHT")
    assert "start_line" not in single
    assert (multi["start_line"], multi["line"], multi["start_side"]) == (5, 7, "RIGHT")
    assert payload["commit_id"] == SHA
    assert payload["event"] == "COMMENT"  # never approves or requests changes


def test_the_most_important_issues_go_inline_and_the_rest_in_the_summary():
    r = report(
        suggestion(line=1, severity="maintainability", title="Tidy"),
        suggestion(line=2, severity="bug", confidence=0.6, title="Unsure bug"),
        suggestion(line=3, severity="security", title="Injection"),
        suggestion(line=4, severity="bug", confidence=0.95, title="Sure bug"),
    )

    inline, rest = split_inline(r, max_comments=2)

    assert [s.line for s in inline] == [3, 4]  # security, then the surer bug
    body = summary(r, max_comments=2)
    assert "Not posted inline (over the limit of 2 comments" in body
    assert "`app.py:2`: Unsure bug" in body and "`app.py:1`: Tidy" in body


def test_the_summary_says_what_was_reviewed_and_what_wasnt():
    body = summary(report(
        suggestion(),
        failed=[FailedChunk(["big.py"], "declined to review this part of the diff", "refused")],
        skipped=[Skipped("uv.lock", "matches an ignored path pattern")],
        dropped_fixes=[DroppedFix("app.py", 3, "it repeats a nearby line")],
    ), review_url="https://github.com/o/r/pull/7#pullrequestreview-1")

    assert body.startswith(MARKER)
    assert "### CodeMop review of abc1234" in body
    assert "Found 1 issue(s) ([comments on the code](https://github.com/o/r/pull/7#pullrequestreview-1)):" in body
    assert "⚠️ Some of this PR wasn't reviewed:\n\n- `big.py`: declined to review this part of the diff" in body
    assert "Skipped `uv.lock`: matches an ignored path pattern" in body
    assert "Left out the suggested fix for `app.py:3`: it repeats a nearby line" in body
    assert "anthropic/claude-opus-5-5 · 2,000 input / 300 output tokens · about $0.02" in body


def test_the_summary_says_when_github_rejected_the_inline_comments():
    assert "GitHub didn't accept the comments on the code" in summary(report(suggestion()), inline_rejected=True)


def test_no_issues():
    r = report()

    assert "No issues found." in summary(r)
    assert split_inline(r) == ([], [])


def comment(body, association="NONE", bot=False):
    return IssueComment(id=1, body=body, author="someone", author_is_bot=bot, author_association=association)


def test_the_summary_comment_records_the_commit_it_describes():
    found = find_summary([comment("Nice PR!"), comment(summary(report()), bot=True)])

    assert reviewed_commit(found) == SHA


def test_only_a_summary_by_a_bot_or_someone_with_write_access_counts():
    """Anyone can comment on a public PR; a forged summary mustn't stop the PR being reviewed"""
    forged = summary(report())

    assert find_summary([comment(forged, association="CONTRIBUTOR")]) is None
    assert find_summary([comment(forged, association="NONE")]) is None
    assert find_summary([comment(forged, association="OWNER")]) is not None
    assert find_summary([comment(forged, bot=True)]) is not None
    assert reviewed_commit(None) is None
