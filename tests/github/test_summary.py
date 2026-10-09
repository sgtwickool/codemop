from codemop.github.api import IssueComment
from codemop.github.summary import (
    ADDRESSED, APPLIED, DISMISSED, MARKER, OPEN, SummaryState, find_summary, read_state, record_applied,
    stored_fixes, summary_body, sync_threads, ticked, update_earlier,
)
from codemop.providers.base import Usage
from codemop.review.chunks import Skipped
from codemop.review.fixes import Fix
from codemop.review.pipeline import DroppedFix, FailedChunk, ReviewReport
from codemop.review.schema import ModelSuggestion

SHA = "abc1234" + "0" * 33
LATER = "def5678" + "0" * 33
SHOWN = {"app.py": {3: "    return result + 1", 5: "x = 1", 6: "y = 2", 7: "z = 3"}, "db.py": {9: "c"}}


def suggestion(line=3, end_line=None, severity="bug", confidence=0.9, title="Adds one to the total",
               code="    return result", path="app.py", group=None):
    return ModelSuggestion(file_path=path, line=line, end_line=end_line, severity=severity, title=title,
                           explanation="Why.", suggested_code=code, confidence=confidence, group=group)


def report(*suggestions, **fields):
    return ReviewReport(model="anthropic/claude-opus-5-5", suggestions=list(suggestions),
                        usage=Usage(input_tokens=2000, output_tokens=300), chunks=1, **fields)


def reviewed(*suggestions, commit=SHA, **options):
    """A first review's state and summary"""
    state = SummaryState(commit=commit)
    state.add(suggestions, SHOWN, commit)
    return state, summary_body(state, report(*suggestions), "about $0.02", **options)


def test_the_summary_keeps_its_findings_and_the_commit():
    state, body = reviewed(suggestion(), suggestion(line=6, title="Other", code=None), checklist=True)

    back = read_state(body)
    assert back.kept and back.commit == SHA
    assert [(f.id, f.title, f.status, f.found_in) for f in back.findings] == [
        (1, "Adds one to the total", OPEN, SHA), (2, "Other", OPEN, SHA),
    ]
    assert back.findings[0].fix == Fix(1, "app.py", 3, 3, "    return result", ["    return result + 1"], "Adds one to the total")
    assert back.findings[1].fix is None


def test_a_checklist_has_a_box_for_each_issue_with_a_fix():
    _, body = reviewed(suggestion(), suggestion(line=5, end_line=7, code=None, title="No fix"), checklist=True)

    assert body.startswith(MARKER)
    assert "2 open issue(s). Tick the fixes you want, and CodeMop commits them to this branch together." in body
    assert "- [ ] 🐛 Bug `app.py:3`: Adds one to the total <!-- codemop-fix:1 -->" in body
    assert "- 🐛 Bug `app.py:5-7`: No fix" in body


def test_no_checklist_without_the_option_or_without_fixes():
    assert "- [ ]" not in reviewed(suggestion())[1]
    assert "- [ ]" not in reviewed(suggestion(code=None), checklist=True)[1]


def test_a_fix_whose_lines_the_diff_doesnt_show_isnt_offered():
    state, _ = reviewed(suggestion(line=40))
    assert state.findings[0].fix is None


def test_the_summary_says_what_was_reviewed_and_what_wasnt():
    state = SummaryState(commit=SHA)
    state.add([suggestion()], SHOWN, SHA)
    body = summary_body(state, report(
        suggestion(),
        failed=[FailedChunk(["big.py"], "declined to review this part of the diff", "refused")],
        skipped=[Skipped("uv.lock", "matches an ignored path pattern")],
        dropped_fixes=[DroppedFix("app.py", 3, "it repeats a nearby line")],
    ), "about $0.02", review_url="https://github.com/o/r/pull/7#pullrequestreview-1", not_commented=2)

    assert "### CodeMop review of abc1234" in body
    assert "1 open issue(s) ([comments on the code](https://github.com/o/r/pull/7#pullrequestreview-1))." in body
    assert "⚠️ Some of this PR wasn't reviewed:\n\n- `big.py`: declined to review this part of the diff" in body
    assert "Skipped `uv.lock`: matches an ignored path pattern" in body
    assert "Left out the suggested fix for `app.py:3`: it repeats a nearby line" in body
    assert "2 issue(s) are listed here without a comment on the code" in body
    assert "anthropic/claude-opus-5-5 · 2,000 input / 300 output tokens · about $0.02" in body


def test_how_to_respond_is_there_when_there_are_issues():
    assert "<summary>How to respond to CodeMop</summary>" in reviewed(suggestion(), checklist=True)[1]
    _, none = reviewed()
    assert "No issues found." in none and "How to respond" not in none


def test_the_summary_says_when_github_rejected_the_inline_comments():
    assert "GitHub didn't accept the comments on the code" in reviewed(suggestion(), inline_rejected=True)[1]


def comment(body, association="NONE", bot=False):
    return IssueComment(id=1, body=body, author="someone", author_is_bot=bot, author_association=association)


def test_only_a_summary_by_a_bot_or_someone_with_write_access_counts():
    """Anyone can comment on a public PR; a forged summary mustn't stop the PR being reviewed"""
    _, forged = reviewed()

    assert find_summary([comment(forged, association="CONTRIBUTOR")]) is None
    assert find_summary([comment(forged, association="NONE")]) is None
    assert find_summary([comment(forged, association="OWNER")]) is not None
    assert read_state(find_summary([comment("Nice PR!"), comment(forged, bot=True)]).body).commit == SHA


def test_a_summary_from_before_findings_were_kept_still_gives_its_commit():
    old = f"{MARKER}\n<!-- codemop-commit: {SHA} -->\n### CodeMop review of abc1234\n\nNo issues found."
    state = read_state(old)
    assert (state.commit, state.findings, state.kept) == (SHA, [], False)


def test_reads_which_fixes_are_ticked_including_from_the_web_page():
    _, body = reviewed(suggestion(), suggestion(line=6, title="Other", code="y = 3"), checklist=True)

    assert ticked(body) == set()
    from_browser = body.replace("- [ ] 🐛 Bug `app.py:6`", "- [x] 🐛 Bug `app.py:6`").replace("\n", "\r\n")
    assert ticked(from_browser) == {2}


def test_records_which_fixes_were_applied_and_which_skipped():
    _, body = reviewed(suggestion(), suggestion(line=6, title="Other", code="y = 3"), checklist=True)
    fixes = stored_fixes(body)
    body = body.replace("- [ ]", "- [x]")

    body = record_applied(body, "fed9876" + "0" * 33, [fixes[1]], [(fixes[2], "the code it replaces has changed")])

    assert "- [x] 🐛 Bug `app.py:3`: Adds one to the total · ✅ applied in fed9876 <!-- codemop-fix:1 -->" in body
    assert "- [ ] 🐛 Bug `app.py:6`: Other · ⚠️ not applied: the code it replaces has changed <!-- codemop-fix:2 -->" in body
    state = read_state(body)
    assert [(f.status, f.note) for f in state.findings] == [(APPLIED, "applied in fed9876"), (OPEN, "")]
    assert list(stored_fixes(body)) == [2]  # only open findings' fixes can be applied
    # Ticked again and skipped again: one note, not two
    body = record_applied(body.replace("- [ ] 🐛 Bug `app.py:6`", "- [x] 🐛 Bug `app.py:6`"), "a" * 40, [], [(fixes[2], "still changed")])
    assert "Other · ⚠️ not applied: still changed <!-- codemop-fix:2 -->" in body


def test_a_group_is_one_item_with_one_checkbox_for_all_its_fixes():
    _, body = reviewed(suggestion(group="g", title="Unclosed session"),
                       suggestion(line=9, path="db.py", code="d", confidence=0.8, group="g", title="Unclosed session"),
                       suggestion(line=5, title="Separate", code="x = 2"), checklist=True)

    # Numbered most important first, so the less sure group member comes after "Separate"
    assert "- [ ] 🐛 Bug Unclosed session (2 places: `app.py:3`, `db.py:9`) <!-- codemop-fix:1,3 -->" in body
    assert "- [ ] 🐛 Bug `app.py:5`: Separate <!-- codemop-fix:2 -->" in body
    assert ticked(body.replace("- [ ] 🐛 Bug Unclosed", "- [x] 🐛 Bug Unclosed")) == {1, 3}


def test_a_group_member_without_a_fix_is_listed_but_not_ticked():
    _, body = reviewed(suggestion(group="g"), suggestion(line=9, path="db.py", code=None, group="g"), checklist=True)

    assert "(2 places: `app.py:3`, `db.py:9`) · fixes for 1 of them <!-- codemop-fix:1 -->" in body


def test_a_group_partly_applied_says_so():
    _, body = reviewed(suggestion(group="g"), suggestion(line=9, path="db.py", code="d", group="g"), checklist=True)
    fixes = stored_fixes(body)

    body = record_applied(body.replace("- [ ]", "- [x]"), "abc9999" + "0" * 33, [fixes[1]],
                          [(fixes[2], "the code it replaces has changed")])

    assert "· ✅ applied in abc9999, except 1: the code it replaces has changed <!-- codemop-fix:1,2 -->" in body


# ---- re-reviews: earlier findings brought up to date ----

HEAD_TEXT = "def total(items):\n    result = sum(items)\n    return result + 1\n"


def test_a_finding_whose_lines_are_gone_and_isnt_raised_again_is_addressed():
    state, _ = reviewed(suggestion())

    new, addressed = update_earlier(state, [], {"app.py": HEAD_TEXT.replace("result + 1", "result")}, SHOWN, LATER)

    assert new == [] and [f.id for f in addressed] == [1]
    assert (state.findings[0].status, state.findings[0].note) == (ADDRESSED, "addressed in def5678")


def test_a_finding_whose_lines_are_still_there_stays_open():
    state, _ = reviewed(suggestion())

    _, addressed = update_earlier(state, [], {"app.py": "# moved down\n" + HEAD_TEXT}, SHOWN, LATER)

    assert addressed == [] and state.findings[0].status == OPEN


def test_a_finding_in_a_deleted_file_is_addressed():
    state, _ = reviewed(suggestion())

    update_earlier(state, [], {"app.py": None}, SHOWN, LATER)

    assert state.findings[0].status == ADDRESSED


def test_a_finding_raised_again_stays_one_finding_with_the_new_location():
    state, _ = reviewed(suggestion())

    new, addressed = update_earlier(state, [suggestion(line=5, code="x = 2")],
                                    {"app.py": "changed\n"}, SHOWN, LATER)  # same title, two lines on

    assert new == [] and addressed == []
    finding = state.findings[0]
    assert (finding.status, finding.line, finding.code, finding.original) == (OPEN, 5, "x = 2", ["x = 1"])


def test_a_finding_raised_again_with_a_reworded_title_is_still_the_same_finding():
    state, _ = reviewed(suggestion())

    new, _ = update_earlier(state, [suggestion(line=5, title="The total adds one", code="x = 2")],
                            {"app.py": "changed\n"}, SHOWN, LATER)

    assert new == [] and len(state.findings) == 1


def test_a_different_issue_nearby_is_a_new_finding():
    """Found by CodeMop on PR #12: a different bug a line away was merged into the old finding"""
    state, _ = reviewed(suggestion())
    other = suggestion(line=5, title="Unvalidated input reaches the query", code="x = 2")

    new, _ = update_earlier(state, [other], {"app.py": HEAD_TEXT}, SHOWN, LATER)

    assert new == [other]
    assert (state.findings[0].line, state.findings[0].code) == (3, "    return result")  # untouched


def test_a_finding_whose_conversation_was_resolved_is_dismissed_and_reopened_if_unresolved():
    state, _ = reviewed(suggestion())

    assert sync_threads(state, [("app.py", "Adds one to the total", True)])
    assert (state.findings[0].status, state.findings[0].note) == (DISMISSED, "dismissed: its conversation was resolved")
    assert not sync_threads(state, [("app.py", "Adds one to the total", True)])  # nothing new

    assert sync_threads(state, [("app.py", "Adds one to the total", False)])
    assert (state.findings[0].status, state.findings[0].note) == (OPEN, "")


def test_resolving_doesnt_touch_applied_or_addressed_findings():
    state, _ = reviewed(suggestion())
    state.findings[0].status = APPLIED

    assert not sync_threads(state, [("app.py", "Adds one to the total", False)])
    assert state.findings[0].status == APPLIED

def test_a_re_review_lists_open_issues_marks_new_ones_and_folds_away_the_done():
    state, _ = reviewed(suggestion(), suggestion(line=6, title="Still here", code=None))
    update_earlier(state, [], {"app.py": "y = 2\n"}, SHOWN, LATER)
    state.add([suggestion(line=7, title="Brand new", code=None)], SHOWN, LATER)
    state.commit = LATER

    body = summary_body(state, report(), "c", since=SHA, less_important=2)

    assert "Reviewed the changes since abc1234." in body
    assert "2 open issue(s)." in body
    assert "- 🐛 Bug `app.py:6`: Still here\n" in body + "\n"
    assert "- 🐛 Bug `app.py:7`: Brand new · new" in body
    assert "<summary>Done (1)</summary>" in body
    assert "- ✅ 🐛 Bug `app.py:3`: Adds one to the total · addressed in def5678" in body
    assert "Left out 2 less important suggestion(s): re-reviews only raise bugs and security issues" in body
