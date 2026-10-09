"""The checklist and codemop apply: ticked fixes committed together."""


from codemop.github import api
from cli_support import (  # noqa: F401
    DIFF, SUGGESTION, FakeModel, run, RecordingModel, TWO_FILE_DIFF, summary_of, tick_all, _async, codemop_comment, learn_reply, posted_with_a_personal_token, new_commit, NEWER, merge_check_on,
)


def test_post_checklist_offers_each_fix_to_tick(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])

    assert "- [ ] 🐛 Bug `app.py:3`: Adds one to the total <!-- codemop-fix:1 -->" in summary_of(github)
    assert "<!-- codemop-state: " in summary_of(github)


def test_no_checklist_on_a_pr_from_a_fork(capsys, monkeypatch, fake_model, github):
    """CodeMop can't commit to a fork's branch, so there's nothing to tick"""
    fake_model([SUGGESTION])
    github["head_repo"] = "someone/fork"

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])

    assert "- [ ]" not in summary_of(github)


def test_apply_commits_the_ticked_fixes_and_marks_them(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    tick_all(github)

    code, out, _ = run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])

    assert code == 0
    assert github["files"]["app.py"] == "def total(items):\n    result = sum(items)\n    return result\n"
    [message] = github["commits"]
    assert message.startswith("Apply CodeMop's suggested fixes\n\n- app.py:3: Adds one to the total")
    assert "Ticked by @maintainer in CodeMop's summary on #7." in message
    assert "· ✅ applied in c0ffee0" in summary_of(github)
    assert "Committed c0ffee0 to feature" in out

    # Run again (another edit of the comment): nothing new to apply
    _, out, _ = run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])
    assert "No ticked fixes to apply on owner/repo#7" in out
    assert len(github["commits"]) == 1


def test_apply_ignores_ticks_by_people_without_write_access(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    tick_all(github)

    code, out, _ = run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "visitor"])

    assert code == 0
    assert "only people with write access to owner/repo can" in out
    assert github["commits"] == []


def test_apply_skips_a_fix_whose_code_has_changed(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    tick_all(github)
    github["files"]["app.py"] = github["files"]["app.py"].replace("result + 1", "result + 2")

    code, out, _ = run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])

    assert code == 0
    assert github["commits"] == []
    assert "- [ ] 🐛 Bug `app.py:3`: Adds one to the total · ⚠️ not applied: the code it replaces has changed" in summary_of(github)
    assert "Not applied app.py:3: the code it replaces has changed since it was reviewed" in out


def test_apply_tries_again_if_the_branch_moves_meanwhile(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    tick_all(github)
    github["branch_moves"] = 1

    code, _, _ = run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])

    assert code == 0
    assert len(github["commits"]) == 1


def test_apply_with_no_summary_or_nothing_ticked(capsys, monkeypatch, fake_model, github):
    _, out, _ = run(capsys, monkeypatch, ["apply", "owner/repo#7"])
    assert "No ticked fixes to apply on owner/repo#7" in out

    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    _, out, _ = run(capsys, monkeypatch, ["apply", "owner/repo#7"])
    assert "No ticked fixes to apply on owner/repo#7" in out


def test_apply_keeps_boxes_ticked_while_it_ran(capsys, monkeypatch, fake_model, github):
    """Found by CodeMop on PR #5: the summary was rewritten from the copy read at the start"""
    fake_model([SUGGESTION, SUGGESTION.model_copy(update={"line": 2, "title": "Second",
                                                          "suggested_code": "    result = sum(items or [])"})])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    [(cid, (body, author, association))] = list(github["comments"].items())
    github["comments"][cid] = (body.replace("- [ ] 🐛 Bug `app.py:3`", "- [x] 🐛 Bug `app.py:3`"), author, association)

    def tick_the_other():
        current = github["comments"][cid][0]
        github["comments"][cid] = (current.replace("- [ ] 🐛 Bug `app.py:2`", "- [x] 🐛 Bug `app.py:2`"), author, association)
    github["while_committing"] = tick_the_other

    run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])

    assert "- [x] 🐛 Bug `app.py:3`: Adds one to the total · ✅ applied in" in summary_of(github)
    assert "- [x] 🐛 Bug `app.py:2`: Second <!-- codemop-fix:" in summary_of(github)  # still ticked, for the next run


def test_one_tick_commits_a_whole_group_across_files(capsys, monkeypatch, fake_model, github):
    """The same mistake in two files: one checklist item, one commit with both fixes"""
    github["files"]["lib.py"] = "def total(items):\n    result = sum(items)\n    return result + 1\n"
    two_files = DIFF + DIFF.replace("app.py", "lib.py")
    monkeypatch.setattr(api, "fetch_pr_diff", lambda *a, **k: _async(two_files))
    fake_model([SUGGESTION.model_copy(update={"group": "off-by-one"}),
                SUGGESTION.model_copy(update={"file_path": "lib.py", "group": "off-by-one"})])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    assert "Adds one to the total (2 places: `app.py:3`, `lib.py:3`) <!-- codemop-fix:1,2 -->" in summary_of(github)
    tick_all(github)

    run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])

    assert len(github["commits"]) == 1
    assert github["files"]["app.py"].endswith("    return result\n") and github["files"]["lib.py"].endswith("    return result\n")
    assert "· ✅ applied in c0ffee0 <!-- codemop-fix:1,2 -->" in summary_of(github)


def test_an_applied_fix_is_listed_as_done_after_the_next_review(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    tick_all(github)
    run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])
    new_commit(github, newer_diff=NEWER)
    fake_model([])

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])

    assert "- ✅ 🐛 Bug `app.py:3`: Adds one to the total · applied in c0ffee0" in summary_of(github)
    assert "- [ ]" not in summary_of(github)
