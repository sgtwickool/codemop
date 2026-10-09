from codemop.github.client import IssueComment
from codemop.github.review import (
    MARKER, comment_body, find_summary, offered_fixes, record_applied, review_payload, reviewed_commit,
    split_inline, stored_fixes, summary_body, ticked,
)
from codemop.review.fixes import Fix
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


def test_an_empty_fix_is_an_empty_suggestion_block_which_deletes_the_lines():
    assert "```suggestion\n```" in comment_body(suggestion(code=""))


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
    assert "Found 1 issue(s) ([comments on the code](https://github.com/o/r/pull/7#pullrequestreview-1))." in body
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


SHOWN = {"app.py": {3: "    return result + 1", 5: "x = 1", 6: "y = 2", 7: "z = 3"}}


def test_a_checklist_has_a_box_for_each_issue_with_a_fix():
    with_fix, without_fix = suggestion(line=3), suggestion(line=5, end_line=7, code=None, title="No fix")
    r = report(with_fix, without_fix)
    fixes = offered_fixes([with_fix, without_fix], SHOWN)

    body = summary_body(r, [with_fix, without_fix], [], "about $0.02", SHA, fixes=fixes, checklist=True)

    assert "Tick the fixes you want, and CodeMop commits them to this branch together." in body
    assert "- [ ] 🐛 Bug `app.py:3`: Adds one to the total <!-- codemop-fix:1 -->" in body
    assert "- 🐛 Bug `app.py:5-7`: No fix" in body
    commit, stored, applied = stored_fixes(body)
    assert commit == SHA and applied == set()
    assert stored == {1: Fix(1, "app.py", 3, 3, "    return result", ["    return result + 1"], "Adds one to the total")}


def test_no_checklist_without_the_option_or_without_fixes():
    s = suggestion()
    fixes = offered_fixes([s], SHOWN)

    assert "- [ ]" not in summary_body(report(s), [s], [], "c", SHA, fixes=fixes)
    assert "- [ ]" not in summary_body(report(s), [s], [], "c", SHA, fixes={}, checklist=True)
    assert stored_fixes(summary_body(report(s), [s], [], "c", SHA, fixes=fixes)) == (None, {}, set())


def test_a_fix_whose_lines_the_diff_doesnt_show_isnt_offered():
    assert offered_fixes([suggestion(line=40)], SHOWN) == {}


def test_reads_which_fixes_are_ticked():
    s1, s2 = suggestion(line=3), suggestion(line=6, title="Other")
    body = summary_body(report(s1, s2), [s1, s2], [], "c", SHA, fixes=offered_fixes([s1, s2], SHOWN), checklist=True)

    assert ticked(body) == set()
    assert ticked(body.replace("- [ ] 🐛 Bug `app.py:6`", "- [x] 🐛 Bug `app.py:6`")) == {2}


def test_ticks_saved_from_githubs_web_page_are_read():
    """Ticking a box in the browser saves the comment with \\r\\n line endings (found by CodeMop on PR #5)"""
    s1 = suggestion(line=3)
    fixes = offered_fixes([s1], SHOWN)
    body = summary_body(report(s1), [s1], [], "c", SHA, fixes=fixes, checklist=True)
    from_browser = body.replace("- [ ]", "- [x]").replace("\n", "\r\n")

    assert ticked(from_browser) == {1}
    assert "· ✅ applied in" in record_applied(from_browser, "a" * 40, [fixes[1]], [])


def test_records_which_fixes_were_applied_and_which_skipped():
    s1, s2 = suggestion(line=3), suggestion(line=6, title="Other")
    fixes = offered_fixes([s1, s2], SHOWN)
    body = summary_body(report(s1, s2), [s1, s2], [], "c", SHA, fixes=fixes, checklist=True).replace("- [ ]", "- [x]")

    body = record_applied(body, "fed9876" + "0" * 33, [fixes[1]], [(fixes[2], "the code it replaces has changed")])

    assert "- [x] 🐛 Bug `app.py:3`: Adds one to the total · ✅ applied in fed9876 <!-- codemop-fix:1 -->" in body
    assert "- [ ] 🐛 Bug `app.py:6`: Other · ⚠️ not applied: the code it replaces has changed <!-- codemop-fix:2 -->" in body
    assert stored_fixes(body)[2] == {1}
    # Ticked again and skipped again: one note, not two
    body = record_applied(body.replace("- [ ] 🐛 Bug `app.py:6`", "- [x] 🐛 Bug `app.py:6`"), "a" * 40, [], [(fixes[2], "still changed")])
    assert "- [ ] 🐛 Bug `app.py:6`: Other · ⚠️ not applied: still changed <!-- codemop-fix:2 -->" in body


def grouped(line, path="app.py", code="fixed()", title="Unclosed session", group="unclosed-sessions", confidence=0.9):
    return ModelSuggestion(file_path=path, line=line, severity="bug", title=title, explanation="Leaks.",
                           suggested_code=code, confidence=confidence, group=group)


GROUP_SHOWN = {"app.py": {3: "a", 5: "b"}, "db.py": {9: "c"}}


def test_a_group_is_one_item_with_one_checkbox_for_all_its_fixes():
    issues = [grouped(3), grouped(9, path="db.py", confidence=0.8), suggestion(line=5, title="Separate")]
    fixes = offered_fixes(issues, GROUP_SHOWN)

    body = summary_body(report(*issues), issues, [], "c", SHA, fixes=fixes, checklist=True)

    assert "- [ ] 🐛 Bug Unclosed session (2 places: `app.py:3`, `db.py:9`) <!-- codemop-fix:1,2 -->" in body
    assert "- [ ] 🐛 Bug `app.py:5`: Separate <!-- codemop-fix:3 -->" in body
    assert ticked(body.replace("- [ ] 🐛 Bug Unclosed", "- [x] 🐛 Bug Unclosed")) == {1, 2}


def test_a_group_split_by_the_comment_limit_is_listed_once():
    issues = [grouped(3), suggestion(line=5, title="Separate", confidence=0.85), grouped(9, path="db.py", confidence=0.5)]
    r = report(*issues)
    inline, rest = split_inline(r, max_comments=2)

    body = summary_body(r, inline, rest, "c", SHA, fixes=offered_fixes([*inline, *rest], GROUP_SHOWN), checklist=True)

    assert body.count("Unclosed session") == 1
    assert "Not posted inline" not in body  # the only one over the limit is listed with its group


def test_a_group_member_without_a_fix_is_listed_but_not_ticked():
    issues = [grouped(3), grouped(9, path="db.py", code=None)]

    body = summary_body(report(*issues), issues, [], "c", SHA, fixes=offered_fixes(issues, GROUP_SHOWN), checklist=True)

    assert "(2 places: `app.py:3`, `db.py:9`) · fixes for 1 of them <!-- codemop-fix:1 -->" in body


def test_inline_comments_in_a_group_say_where_else_the_problem_is():
    issues = [grouped(3), grouped(9, path="db.py")]

    first, second = review_payload(issues, SHA, issues)["comments"]

    assert "The same problem is also at `db.py:9`; the summary has one fix for them all." in first["body"]
    assert "also at `app.py:3`" in second["body"]
    assert "also at" not in review_payload([suggestion()], SHA, [suggestion()])["comments"][0]["body"]


def test_a_group_partly_applied_says_so():
    issues = [grouped(3), grouped(9, path="db.py")]
    fixes = offered_fixes(issues, GROUP_SHOWN)
    body = summary_body(report(*issues), issues, [], "c", SHA, fixes=fixes, checklist=True).replace("- [ ]", "- [x]")

    body = record_applied(body, "abc9999" + "0" * 33, [fixes[1]], [(fixes[2], "the code it replaces has changed")])

    assert "· ✅ applied in abc9999, except 1: the code it replaces has changed <!-- codemop-fix:1,2 -->" in body
