"""Responding to CodeMop: resolving conversations, and /codemop learn."""


from codemop import providers
from codemop.github.api import ReviewComment, ReviewThread
from codemop.review.learned import parse_learned
from cli_support import (  # noqa: F401
    DIFF, SUGGESTION, FakeModel, run, RecordingModel, TWO_FILE_DIFF, summary_of, tick_all, _async, codemop_comment, learn_reply, posted_with_a_personal_token, new_commit, NEWER, merge_check_on,
)


def test_a_resolved_comment_isnt_raised_again(capsys, monkeypatch, fake_model, github):
    codemop_comment(github)
    github["threads"][0] = github["threads"][0].__class__(**{**github["threads"][0].__dict__, "resolved": True})
    fake_model([SUGGESTION.model_copy(update={"line": 2})])  # the same issue, a line away after an edit

    code, out, _ = run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert code == 0
    assert "No issues found." in summary_of(github)
    assert "Left out 1 suggestion(s) dismissed earlier on this pull request" in out


def test_the_model_is_told_whats_settled(capsys, monkeypatch, github):
    """Learned notes come from the default branch; dismissed issues from resolved conversations"""
    codemop_comment(github)
    github["threads"][0] = github["threads"][0].__class__(**{**github["threads"][0].__dict__, "resolved": True})
    github["default_branch"][".codemop-learned.yml"] = "- path: db.py\n  issue: Float money\n  reason: Cents are ints\n"
    seen = []

    class Recording(FakeModel):
        async def review(self, instructions, diff_text):
            seen.append(instructions)
            return await super().review(instructions, diff_text)
    monkeypatch.setattr(providers, "create_model", lambda *a, **k: Recording([]))

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert "These have already been settled by the people reviewing this code" in seen[0]
    assert "- In db.py: Float money. It's fine here: Cents are ints" in seen[0]
    assert "- In app.py near line 3: Adds one to the total. Dismissed on this pull request" in seen[0]


def test_learn_adds_a_note_resolves_the_conversation_and_says_so(capsys, monkeypatch, github):
    codemop_comment(github)
    reply = learn_reply(github, "/codemop learn The +1 is the header row, which the total includes")

    code, _, _ = run(capsys, monkeypatch, ["learn", "owner/repo#7", "--comment", str(reply)])

    assert code == 0
    learned = github["files"][".codemop-learned.yml"]
    assert learned.startswith("# What this repository's reviewers have told CodeMop isn't a problem here.")
    assert "- path: app.py\n  issue: Adds one to the total\n  reason: The +1 is the header row, which the total includes\n  from: '#7, @maintainer'" in learned
    assert github["commits"][0].startswith("Teach CodeMop: Adds one to the total")
    assert github["resolved"] == ["thread-500"]
    [(to, text)] = github["replies"]
    assert to == reply
    assert text.startswith("Learned: I've added this to `.codemop-learned.yml` on this branch (c0ffee0)")


def test_learn_adds_to_an_existing_file(capsys, monkeypatch, github):
    codemop_comment(github)
    github["files"][".codemop-learned.yml"] = "# my notes\n- path: x.py\n  issue: A\n  reason: B\n"
    run(capsys, monkeypatch, ["learn", "owner/repo#7", "--comment", str(learn_reply(github, "/codemop learn fine"))])

    learned = github["files"][".codemop-learned.yml"]
    assert learned.startswith("# my notes\n- path: x.py")
    assert [e.issue for e in parse_learned(learned)] == ["A", "Adds one to the total"]


def test_learn_needs_a_reason(capsys, monkeypatch, github):
    codemop_comment(github)

    run(capsys, monkeypatch, ["learn", "owner/repo#7", "--comment", str(learn_reply(github, "/codemop learn"))])

    assert github["commits"] == [] and github["resolved"] == []
    assert "Say why it's fine" in github["replies"][0][1]


def test_learn_is_only_for_people_with_write_access(capsys, monkeypatch, github):
    codemop_comment(github)

    run(capsys, monkeypatch, ["learn", "owner/repo#7", "--comment",
                              str(learn_reply(github, "/codemop learn trust me", author="visitor"))])

    assert github["commits"] == [] and github["resolved"] == []
    assert "Only people with write access to owner/repo can teach CodeMop" in github["replies"][0][1]


def test_learn_ignores_replies_to_other_peoples_comments(capsys, monkeypatch, github):
    github["review_comments"][500] = ReviewComment(500, "I think this is wrong", "app.py", 3, None, "sam", False)

    _, out, _ = run(capsys, monkeypatch, ["learn", "owner/repo#7", "--comment",
                                         str(learn_reply(github, "/codemop learn because"))])

    assert github["replies"] == [] and github["commits"] == []
    assert "Not a `/codemop learn` reply to one of CodeMop's comments" in out


def test_learn_on_a_fork_resolves_and_says_how_to_add_the_note(capsys, monkeypatch, github):
    codemop_comment(github)
    github["head_repo"] = "someone/fork"

    run(capsys, monkeypatch, ["learn", "owner/repo#7", "--comment", str(learn_reply(github, "/codemop learn fine here"))])

    assert github["commits"] == []
    assert github["resolved"] == ["thread-500"]
    text = github["replies"][0][1]
    assert "I can't commit to a fork's branch" in text
    assert "```yaml\n- path: app.py\n  issue: Adds one to the total\n  reason: fine here" in text


def test_learn_works_when_codemop_posts_with_a_personal_access_token(capsys, monkeypatch, github):
    """Found by CodeMop on PR #10: its comments were only recognised when posted by a bot"""
    codemop_comment(github)
    posted_with_a_personal_token(github)

    run(capsys, monkeypatch, ["learn", "owner/repo#7", "--comment", str(learn_reply(github, "/codemop learn fine"))])

    assert github["replies"][0][1].startswith("Learned:")


def test_resolving_works_when_codemop_posts_with_a_personal_access_token(capsys, monkeypatch, fake_model, github):
    codemop_comment(github)
    posted_with_a_personal_token(github)
    github["threads"][0] = ReviewThread(**{**github["threads"][0].__dict__, "resolved": True})
    fake_model([SUGGESTION])

    _, out, _ = run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert "Left out 1 suggestion(s) dismissed earlier on this pull request" in out


def test_a_copy_of_codemops_comment_by_an_outsider_isnt_trusted(capsys, monkeypatch, github):
    codemop_comment(github)
    old = github["review_comments"][500]
    github["review_comments"][500] = ReviewComment(old.id, old.body, old.path, old.line, None, "mallory", False, "CONTRIBUTOR")

    _, out, _ = run(capsys, monkeypatch, ["learn", "owner/repo#7", "--comment", str(learn_reply(github, "/codemop learn x"))])

    assert "Not a `/codemop learn` reply to one of CodeMop's comments" in out
