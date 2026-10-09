from codemop.github.review import comment_body, parse_comment, ranked, review_payload
from codemop.review.schema import ModelSuggestion

SHA = "abc1234" + "0" * 33


def suggestion(line=3, end_line=None, severity="bug", confidence=0.9, title="Adds one to the total", code="    return result"):
    return ModelSuggestion(file_path="app.py", line=line, end_line=end_line, severity=severity, title=title,
                           explanation="The +1 looks accidental.", suggested_code=code, confidence=confidence)


def test_a_comment_with_a_fix_has_a_suggestion_block():
    assert comment_body(suggestion()) == (
        "**🐛 Bug: Adds one to the total**\n\nThe +1 looks accidental.\n\n"
        "```suggestion\n    return result\n```\n\n<sub>CodeMop · confidence 0.90 · Not a problem? Resolve this "
        "conversation and CodeMop won't raise it again on this PR, or reply `/codemop learn <why>` to teach it "
        "for the whole repository.</sub>"
    )


def test_an_empty_fix_is_an_empty_suggestion_block_which_deletes_the_lines():
    assert "```suggestion\n```" in comment_body(suggestion(code=""))


def test_a_comment_without_a_fix_has_no_suggestion_block():
    assert "suggestion" not in comment_body(suggestion(code=None)).split("<sub>")[0]


def test_backticks_in_the_fix_get_a_longer_fence():
    body = comment_body(suggestion(code='doc = """\n```python\nx\n```\n"""'))
    assert "````suggestion\n" in body and body.count("````") == 2


def test_inline_comments_point_at_the_lines_on_the_new_side():
    payload = review_payload([suggestion(line=3), suggestion(line=5, end_line=7)], SHA)

    single, multi = payload["comments"]
    assert (single["path"], single["line"], single["side"]) == ("app.py", 3, "RIGHT")
    assert "start_line" not in single
    assert (multi["start_line"], multi["line"], multi["start_side"]) == (5, 7, "RIGHT")
    assert payload["commit_id"] == SHA
    assert payload["event"] == "COMMENT"  # never approves or requests changes


def grouped(line, path="app.py", code="fixed()", title="Unclosed session", group="unclosed-sessions", confidence=0.9):
    return ModelSuggestion(file_path=path, line=line, severity="bug", title=title, explanation="Leaks.",
                           suggested_code=code, confidence=confidence, group=group)


def test_inline_comments_in_a_group_say_where_else_the_problem_is():
    issues = [grouped(3), grouped(9, path="db.py")]

    first, second = review_payload(issues, SHA, issues)["comments"]

    assert "The same problem is also at `db.py:9`; the summary has one fix for them all." in first["body"]
    assert "also at `app.py:3`" in second["body"]
    assert "also at" not in review_payload([suggestion()], SHA, [suggestion()])["comments"][0]["body"]




def test_reads_its_own_comments_back():
    assert parse_comment(comment_body(suggestion())) == ("bug", "Adds one to the total")
    assert parse_comment("**🐛 Bug: Looks like ours** but has no footer") is None


def test_most_important_first():
    issues = [suggestion(line=1, severity="maintainability"), suggestion(line=2, confidence=0.6),
              suggestion(line=3, severity="security"), suggestion(line=4, confidence=0.95)]

    assert [s.line for s in ranked(issues)] == [3, 4, 2, 1]
