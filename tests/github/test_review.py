from codemop.github.review import MARKER, already_reviewed, comment_body, review_payload
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


def test_inline_comments_point_at_the_lines_on_the_new_side():
    payload = review_payload(report(suggestion(line=3), suggestion(line=5, end_line=7)), SHA, "about $0.02")

    single, multi = payload["comments"]
    assert (single["path"], single["line"], single["side"]) == ("app.py", 3, "RIGHT")
    assert "start_line" not in single
    assert (multi["start_line"], multi["line"], multi["start_side"]) == (5, 7, "RIGHT")
    assert payload["commit_id"] == SHA
    assert payload["event"] == "COMMENT"  # never approves or requests changes


def test_the_most_important_issues_go_inline_and_the_rest_in_the_summary():
    issues = [
        suggestion(line=1, severity="maintainability", title="Tidy"),
        suggestion(line=2, severity="bug", confidence=0.6, title="Unsure bug"),
        suggestion(line=3, severity="security", title="Injection"),
        suggestion(line=4, severity="bug", confidence=0.95, title="Sure bug"),
    ]

    payload = review_payload(report(*issues), SHA, "about $0.02", max_comments=2)

    assert [c["line"] for c in payload["comments"]] == [3, 4]  # security, then the surer bug
    assert "Not posted inline (over the limit of 2 comments" in payload["body"]
    assert "`app.py:2`: Unsure bug" in payload["body"] and "`app.py:1`: Tidy" in payload["body"]


def test_the_summary_says_what_was_reviewed_and_what_wasnt():
    body = review_payload(report(
        suggestion(),
        failed=[FailedChunk(["big.py"], "declined to review this part of the diff", "refused")],
        skipped=[Skipped("uv.lock", "matches an ignored path pattern")],
        dropped_fixes=[DroppedFix("app.py", 3, "it repeats a nearby line")],
    ), SHA, "about $0.02")["body"]

    assert body.startswith(MARKER)
    assert "### CodeMop review of abc1234" in body
    assert "Found 1 issue(s):" in body
    assert "⚠️ Some of this PR wasn't reviewed:\n\n- `big.py`: declined to review this part of the diff" in body
    assert "Skipped `uv.lock`: matches an ignored path pattern" in body
    assert "Left out the suggested fix for `app.py:3`: it repeats a nearby line" in body
    assert "anthropic/claude-opus-5-5 · 2,000 input / 300 output tokens · about $0.02" in body


def test_no_issues():
    payload = review_payload(report(), SHA, "about $0.01")

    assert "No issues found." in payload["body"]
    assert payload["comments"] == []


def test_a_commit_already_reviewed_by_codemop_is_recognised():
    body = review_payload(report(), SHA, "about $0.01")["body"]

    assert already_reviewed([("other", "LGTM"), (SHA, body)], SHA)
    assert not already_reviewed([("0" * 40, body)], SHA)  # an earlier commit
    assert not already_reviewed([(SHA, "A person's review")], SHA)
