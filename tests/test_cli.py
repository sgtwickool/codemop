"""
The codemop command, with a fake model and a fake GitHub.
"""
import io
import json

import pytest

from codemop import cli
from codemop.github.client import GitHubError, IssueComment, PullRequest, ReviewComment, ReviewThread
from codemop.review.learned import parse_learned
from codemop.providers.base import NoReview, Usage
from codemop.review.schema import ModelReview, ModelSuggestion

DIFF = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 def total(items):
-    return sum(items)
+    result = sum(items)
+    return result + 1
"""

SUGGESTION = ModelSuggestion(
    file_path="app.py", line=3, severity="bug", title="Adds one to the total",
    explanation="The +1 changes the result; it looks accidental.", suggested_code="    return result",
    confidence=0.9,
)


class FakeModel:
    name = "fake/model"
    chunk_tokens = 40_000

    def cost(self, usage):
        return usage.input_tokens * 10 / 1_000_000  # $10 per million input tokens

    def __init__(self, result):
        self.result = result

    async def review(self, instructions, diff_text):
        if isinstance(self.result, Exception):
            raise self.result
        return ModelReview(suggestions=self.result), Usage(input_tokens=1234, output_tokens=56)


@pytest.fixture(autouse=True)
def no_repo_config(monkeypatch):
    """Repositories have no .codemop.yml unless a test says so (and nothing reaches GitHub)"""
    files = {}

    async def fake_fetch_repo_file(repo, path, token=None, api_url=None):
        return files.get((repo, path))

    async def no_threads(pr, token=None, api_url=None):
        return []
    monkeypatch.setattr(cli, "fetch_repo_file", fake_fetch_repo_file)
    monkeypatch.setattr(cli, "list_review_threads", no_threads)
    return files


@pytest.fixture
def fake_model(monkeypatch):
    def use(result):
        monkeypatch.setattr(cli, "create_model", lambda *a, **k: FakeModel(result))
    return use


def run(capsys, monkeypatch, argv, stdin=""):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_reviews_a_diff_from_stdin(capsys, monkeypatch, fake_model):
    fake_model([SUGGESTION])

    code, out, _ = run(capsys, monkeypatch, ["review", "-"], stdin=DIFF)

    assert code == 0
    assert "CodeMop review of stdin with fake/model" in out
    assert "app.py:3  [bug, confidence 0.90]  Adds one to the total" in out
    assert "      return result" in out
    assert "1 suggestion(s) · 1 chunk(s) · 1,234 input / 56 output tokens · about $0.01 (list prices as of 2026-09-25)" in out


def test_json_output(capsys, monkeypatch, fake_model):
    fake_model([SUGGESTION])

    code, out, _ = run(capsys, monkeypatch, ["review", "-", "--json"], stdin=DIFF)

    data = json.loads(out)
    assert code == 0
    assert data["complete"] is True
    assert data["suggestions"][0]["severity"] == "bug"
    assert data["usage"]["input_tokens"] == 1234


def test_min_confidence(capsys, monkeypatch, fake_model):
    fake_model([SUGGESTION.model_copy(update={"confidence": 0.4})])

    _, out, _ = run(capsys, monkeypatch, ["review", "-"], stdin=DIFF)

    assert "No issues found." in out
    assert "Dropped 1 suggestion(s) below the confidence threshold" in out


def test_an_incomplete_review_exits_1_and_says_why(capsys, monkeypatch, fake_model):
    fake_model(NoReview("Anthropic rejected the API key: check ANTHROPIC_API_KEY", fatal=True))

    code, out, _ = run(capsys, monkeypatch, ["review", "-"], stdin=DIFF)

    assert code == 1
    assert "Stopped early: Anthropic rejected the API key: check ANTHROPIC_API_KEY (not reviewed: app.py)" in out
    assert out.count("rejected the API key") == 1
    assert "No issues found in the parts that were reviewed." in out
    assert "0 input / 0 output tokens · nothing spent" in out  # not "no cost (local model)"


def test_reviews_a_pull_request(capsys, monkeypatch, fake_model):
    fake_model([SUGGESTION])
    fetched = {}

    async def fake_fetch(pr, token=None, api_url=None):
        fetched.update(pr=str(pr), token=token)
        return DIFF
    monkeypatch.setattr(cli, "fetch_pr_diff", fake_fetch)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")

    code, out, _ = run(capsys, monkeypatch, ["review", "https://github.com/owner/repo/pull/7"])

    assert code == 0
    assert fetched == {"pr": "owner/repo#7", "token": "ghp_test"}
    assert "CodeMop review of owner/repo#7" in out


def test_github_errors_are_shown(capsys, monkeypatch, fake_model):
    fake_model([])

    async def failing_fetch(*a, **k):
        raise GitHubError("GitHub returned 404 for owner/repo#7: if the repository is private, set GITHUB_TOKEN")
    monkeypatch.setattr(cli, "fetch_pr_diff", failing_fetch)
    monkeypatch.setenv("GITHUB_TOKEN", "x")

    code, _, err = run(capsys, monkeypatch, ["review", "owner/repo#7"])

    assert code == 1
    assert "codemop: GitHub returned 404" in err


@pytest.mark.parametrize("argv, message", [
    (["review", "not-a-pr"], "Not a pull request"),
    (["review", "-", "--provider", "openai"], "Name a model for openai"),
])
def test_usage_errors_exit_2(capsys, monkeypatch, argv, message):
    code, _, err = run(capsys, monkeypatch, argv, stdin=DIFF)

    assert code == 2
    assert message in err


def test_github_token_falls_back_to_gh(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/gh")
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return type("R", (), {"returncode": 0, "stdout": "gho_abc\n"})()
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli.github_token() == "gho_abc"
    assert calls == [["/usr/bin/gh", "auth", "token"]]  # the resolved path, not whatever "gh" is on PATH later


class RecordingModel(FakeModel):
    """Remembers what review_diff was asked to do, via the chunks it receives"""
    seen = []

    async def review(self, instructions, diff_text):
        RecordingModel.seen.append(diff_text)
        return await super().review(instructions, diff_text)


TWO_FILE_DIFF = DIFF + """\
diff --git a/docs/guide.md b/docs/guide.md
--- a/docs/guide.md
+++ b/docs/guide.md
@@ -1 +1 @@
-old
+new
"""


@pytest.fixture
def pr_diff(monkeypatch):
    async def fake_fetch(pr, token=None, api_url=None):
        return TWO_FILE_DIFF
    monkeypatch.setattr(cli, "fetch_pr_diff", fake_fetch)
    monkeypatch.setenv("GITHUB_TOKEN", "x")


def test_the_repositorys_config_is_used(capsys, monkeypatch, fake_model, no_repo_config, pr_diff):
    fake_model([SUGGESTION.model_copy(update={"confidence": 0.6})])
    no_repo_config[("owner/repo", ".codemop.yml")] = "min_confidence: 0.7\nignore: ['docs/*']\n"

    _, out, _ = run(capsys, monkeypatch, ["review", "owner/repo#7"])

    assert "(settings from owner/repo/.codemop.yml)" in out
    assert "Skipped docs/guide.md: matches an ignored path pattern" in out
    assert "Dropped 1 suggestion(s) below the confidence threshold" in out  # 0.6 < 0.7


def test_flags_override_the_repositorys_config(capsys, monkeypatch, fake_model, no_repo_config, pr_diff):
    fake_model([SUGGESTION.model_copy(update={"confidence": 0.6})])
    no_repo_config[("owner/repo", ".codemop.yml")] = "min_confidence: 0.7\n"

    _, out, _ = run(capsys, monkeypatch, ["review", "owner/repo#7", "--min-confidence", "0.5"])

    assert "app.py:3" in out


def test_ignore_flags_add_to_the_defaults_and_the_config(capsys, monkeypatch, fake_model, no_repo_config, pr_diff):
    fake_model([])

    _, out, _ = run(capsys, monkeypatch, ["review", "owner/repo#7", "--ignore", "docs/*"])

    assert "Skipped docs/guide.md: matches an ignored path pattern" in out


def test_an_invalid_config_stops_with_its_problems(capsys, monkeypatch, fake_model, no_repo_config, pr_diff):
    fake_model([])
    no_repo_config[("owner/repo", ".codemop.yml")] = "provider: openai-compatible\n"

    code, _, err = run(capsys, monkeypatch, ["review", "owner/repo#7"])

    assert code == 2
    assert "owner/repo/.codemop.yml: unknown setting `provider`" in err


def test_stdin_uses_the_config_in_the_current_directory(capsys, monkeypatch, fake_model, tmp_path):
    fake_model([SUGGESTION.model_copy(update={"confidence": 0.6})])
    (tmp_path / ".codemop.yml").write_text("min_confidence: 0.9\n")
    monkeypatch.chdir(tmp_path)

    _, out, _ = run(capsys, monkeypatch, ["review", "-"], stdin=DIFF)

    assert "(settings from .codemop.yml)" in out
    assert "No issues found." in out


def test_an_explicit_config_file(capsys, monkeypatch, fake_model, tmp_path):
    fake_model([])
    config = tmp_path / "review.yml"
    config.write_text("min_confidence: 0.9\n")

    _, out, _ = run(capsys, monkeypatch, ["review", "-", "--config", str(config)], stdin=DIFF)
    code, _, err = run(capsys, monkeypatch, ["review", "-", "--config", str(tmp_path / "missing.yml")], stdin=DIFF)

    assert f"(settings from {config})" in out
    assert code == 2 and "missing.yml doesn't exist" in err


def test_the_model_comes_from_codemop_variables(capsys, monkeypatch):
    chosen = {}

    def fake_create_model(provider, model, **kwargs):
        chosen.update(provider=provider, model=model, base_url=kwargs.get("base_url"))
        return FakeModel([])
    monkeypatch.setattr(cli, "create_model", fake_create_model)
    monkeypatch.setenv("CODEMOP_PROVIDER", "ollama")
    monkeypatch.setenv("CODEMOP_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("CODEMOP_BASE_URL", "http://gpu-box:11434/v1")

    run(capsys, monkeypatch, ["review", "-"], stdin=DIFF)

    assert chosen == {"provider": "ollama", "model": "qwen2.5-coder:7b", "base_url": "http://gpu-box:11434/v1"}


@pytest.fixture
def github(monkeypatch):
    """
    A fake GitHub for --post: one open PR at commit abc..., the reviews posted to it, and its
    conversation comments (by id)
    """
    state = {
        "head": "abc1234" + "0" * 33, "head_repo": "owner/repo", "reviews": [], "comments": {}, "reject_inline": False,
        "files": {"app.py": "def total(items):\n    result = sum(items)\n    return result + 1\n"},
        "commits": [], "permissions": {"maintainer": "write", "visitor": "read"}, "branch_moves": 0,
        "while_committing": None,  # something to happen to the PR while fixes are being committed
        "default_branch": {},  # files on the default branch (the PR's are in "files")
        "threads": [], "review_comments": {}, "replies": [], "resolved": [],
        "newer_diff": None,  # what's changed since the last review, if it's an ancestor of the head
    }

    async def fetch_pull_request(pr, token=None, api_url=None):
        return PullRequest(head_sha=state["head"], state="open", draft=False, head_ref="feature",
                           head_repo=state["head_repo"])

    async def fetch_repo_file(repo, path, ref=None, token=None, api_url=None):
        return state["files"].get(path) if ref else state["default_branch"].get(path)

    async def list_review_threads(pr, token=None, api_url=None):
        return list(state["threads"])

    async def compare_commits(repo, base, head, token=None, api_url=None):
        return state["newer_diff"]

    async def fetch_review_comment(repo, comment_id, token=None, api_url=None):
        return state["review_comments"].get(comment_id)

    async def reply_to_review_comment(pr, comment_id, body, token=None, api_url=None):
        state["replies"].append((comment_id, body))
        return "https://github.com/reply"

    async def resolve_thread(thread_id, token=None, api_url=None):
        state["resolved"].append(thread_id)

    async def user_permission(repo, user, token=None, api_url=None):
        return state["permissions"].get(user, "none")

    async def commit_files(repo, branch, parent_sha, files, message, token=None, api_url=None):
        if state["branch_moves"]:
            state["branch_moves"] -= 1
            state["head"] = "moved00" + "0" * 33
            raise GitHubError("the branch moved", 422)
        assert (repo, branch, parent_sha) == (state["head_repo"], "feature", state["head"])
        if state["while_committing"]:
            state["while_committing"]()
        state["files"].update(files)
        state["commits"].append(message)
        state["head"] = "c0ffee0" + "0" * 33
        return state["head"]

    async def list_issue_comments(pr, token=None, api_url=None):
        return [IssueComment(id=i, body=body, author=author, author_is_bot=author.endswith("[bot]"),
                             author_association=association)
                for i, (body, author, association) in state["comments"].items()]

    async def fetch_pr_diff(pr, token=None, api_url=None):
        return DIFF

    async def post_review(pr, review, token=None, api_url=None):
        if state["reject_inline"]:
            raise GitHubError("GitHub rejected the review", 422)
        state["reviews"].append(review)
        return f"https://github.com/owner/repo/pull/7#pullrequestreview-{len(state['reviews'])}"

    async def post_issue_comment(pr, body, comment_id=None, token=None, api_url=None):
        comment_id = comment_id or len(state["comments"]) + 100
        state["comments"][comment_id] = (body, "github-actions[bot]", "NONE")
        return f"https://github.com/owner/repo/pull/7#issuecomment-{comment_id}"

    for name, fake in [("fetch_pull_request", fetch_pull_request), ("list_issue_comments", list_issue_comments),
                       ("fetch_pr_diff", fetch_pr_diff), ("post_review", post_review),
                       ("post_issue_comment", post_issue_comment), ("fetch_repo_file", fetch_repo_file),
                       ("user_permission", user_permission), ("commit_files", commit_files),
                       ("list_review_threads", list_review_threads), ("fetch_review_comment", fetch_review_comment),
                       ("reply_to_review_comment", reply_to_review_comment), ("resolve_thread", resolve_thread),
                       ("compare_commits", compare_commits)]:
        monkeypatch.setattr(cli, name, fake)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    return state


def summary_of(github):
    [(body, _, _)] = [c for c in github["comments"].values() if "codemop-summary" in c[0]]
    return body


def test_post_posts_the_comments_as_a_review_and_a_summary(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])

    code, out, _ = run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert code == 0
    [review] = github["reviews"]
    assert review["commit_id"] == github["head"]
    assert [(c["path"], c["line"]) for c in review["comments"]] == [("app.py", 3)]
    assert "```suggestion\n    return result\n```" in review["comments"][0]["body"]
    assert "1 open issue(s) ([comments on the code](https://github.com/owner/repo/pull/7#pullrequestreview-1))" in summary_of(github)
    assert "Posted the review: https://github.com/owner/repo/pull/7#issuecomment-100" in out


def test_post_doesnt_review_a_commit_twice(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])
    fake_model(AssertionError("the model shouldn't be asked again"))

    code, out, _ = run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert code == 0
    assert "CodeMop has already reviewed owner/repo#7 at abc1234; nothing to do" in out
    assert len(github["reviews"]) == 1


def test_a_new_commit_updates_the_summary_in_place(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])
    github["head"] = "def5678" + "0" * 33
    fake_model([])

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert list(github["comments"]) == [100]  # the same comment, edited
    assert "### CodeMop review of def5678" in summary_of(github)
    assert "1 open issue(s)" in summary_of(github)  # its code hasn't changed, so it's still open
    assert len(github["reviews"]) == 1  # no new issues, so no second review


def test_a_forged_summary_doesnt_stop_the_review(capsys, monkeypatch, fake_model, github):
    """Anyone can comment on a public PR, including a copy of a summary claiming this commit"""
    github["comments"][1] = (f"<!-- codemop-summary -->\n<!-- codemop-commit: {github['head']} -->", "mallory", "CONTRIBUTOR")
    fake_model([SUGGESTION])

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert len(github["reviews"]) == 1


def test_post_lists_the_issues_in_the_summary_if_github_rejects_the_inline_comments(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    github["reject_inline"] = True

    code, _, _ = run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert code == 0
    assert github["reviews"] == []
    assert "`app.py:3`: Adds one to the total" in summary_of(github)
    assert "GitHub didn't accept the comments on the code" in summary_of(github)


def test_post_limits_inline_comments(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION, SUGGESTION.model_copy(update={"line": 2, "title": "Second"})])

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--max-comments", "1"])

    [review] = github["reviews"]
    assert len(review["comments"]) == 1
    assert "`app.py:2`: Second" in summary_of(github)


def test_post_posts_nothing_when_the_review_stopped(capsys, monkeypatch, fake_model, github):
    fake_model(NoReview("Anthropic rejected the API key: check ANTHROPIC_API_KEY", fatal=True))

    code, _, err = run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert code == 1
    assert github["reviews"] == [] and github["comments"] == {}
    assert "not posting a review: Anthropic rejected the API key" in err


@pytest.mark.parametrize("argv, expected", [
    (["review", "-", "--post"], "--post needs a pull request to post on, not a diff"),
    (["review", "owner/repo#7", "--post"], "--post needs a GitHub token"),
])
def test_post_needs_a_pull_request_and_a_token(capsys, monkeypatch, fake_model, argv, expected):
    fake_model([SUGGESTION])
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)  # no gh login either

    code, _, err = run(capsys, monkeypatch, argv, stdin=DIFF)

    assert code == 2
    assert expected in err


def test_a_diff_over_the_limit_is_not_reviewed_and_exits_0(capsys, monkeypatch, fake_model):
    fake_model(AssertionError("the model shouldn't be asked"))

    code, out, _ = run(capsys, monkeypatch, ["review", "-", "--max-changed-lines", "1"], stdin=DIFF)

    assert code == 0
    assert "Not reviewed: 3 changed lines to review, more than the limit of 1." in out
    assert "nothing spent" in out


def test_post_says_when_a_pr_was_too_large_to_review(capsys, monkeypatch, fake_model, github):
    fake_model(AssertionError("the model shouldn't be asked"))

    code, _, _ = run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--max-changed-lines", "1"])

    assert code == 0
    assert github["reviews"] == []
    assert "Not reviewed: this PR has 3 changed lines to review, more than the limit of 1 set for CodeMop here." in summary_of(github)


def tick_all(github):
    [(cid, (body, author, association))] = [(i, c) for i, c in github["comments"].items() if "codemop-summary" in c[0]]
    github["comments"][cid] = (body.replace("- [ ]", "- [x]"), author, association)


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
    monkeypatch.setattr(cli, "fetch_pr_diff", lambda *a, **k: _async(two_files))
    fake_model([SUGGESTION.model_copy(update={"group": "off-by-one"}),
                SUGGESTION.model_copy(update={"file_path": "lib.py", "group": "off-by-one"})])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])
    assert "Adds one to the total (2 places: `app.py:3`, `lib.py:3`) <!-- codemop-fix:1,2 -->" in summary_of(github)
    tick_all(github)

    run(capsys, monkeypatch, ["apply", "owner/repo#7", "--by", "maintainer"])

    assert len(github["commits"]) == 1
    assert github["files"]["app.py"].endswith("    return result\n") and github["files"]["lib.py"].endswith("    return result\n")
    assert "· ✅ applied in c0ffee0 <!-- codemop-fix:1,2 -->" in summary_of(github)


async def _async(value):
    return value


def codemop_comment(github, comment_id=500, path="app.py", line=3):
    """One of CodeMop's comments on the code, as posted, in its own thread"""
    body = cli.review_payload([SUGGESTION.model_copy(update={"file_path": path, "line": line})], github["head"])["comments"][0]["body"]
    github["review_comments"][comment_id] = ReviewComment(comment_id, body, path, line, None, "github-actions[bot]", True)
    github["threads"].append(ReviewThread(f"thread-{comment_id}", False, path, line, comment_id, body, True, "NONE"))
    return comment_id


def learn_reply(github, text, author="maintainer", reply_id=501, to=500):
    github["review_comments"][reply_id] = ReviewComment(reply_id, text, "app.py", 3, to, author, False)
    return reply_id


def test_every_comment_says_how_to_respond(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])

    comment = github["reviews"][0]["comments"][0]["body"]
    assert "Not a problem? Resolve this conversation and CodeMop won't raise it again on this PR" in comment
    assert "reply `/codemop learn <why>`" in comment
    summary = summary_of(github)
    assert "<summary>How to respond to CodeMop</summary>" in summary
    assert "**Fix it:** tick its box above" in summary
    assert "**Not a problem here:** resolve the comment's conversation" in summary
    assert "**Not a problem anywhere in this repository:** reply `/codemop learn <why it's fine>`" in summary


def test_on_a_fork_the_summary_says_what_works_there(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    github["head_repo"] = "someone/fork"

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post", "--checklist"])

    assert "**Fix it:** use \"Commit suggestion\" on its comment" in summary_of(github)
    assert "CodeMop can't commit to a fork's branch, so add a note to `.codemop-learned.yml`" in summary_of(github)


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
    monkeypatch.setattr(cli, "create_model", lambda *a, **k: Recording([]))

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


def posted_with_a_personal_token(github, comment_id=500):
    """CodeMop's comment as posted with a maintainer's personal access token: by them, not a bot"""
    old = github["review_comments"][comment_id]
    github["review_comments"][comment_id] = ReviewComment(old.id, old.body, old.path, old.line, None, "maintainer", False, "OWNER")
    github["threads"][0] = ReviewThread(**{**github["threads"][0].__dict__, "first_comment_by_bot": False,
                                           "first_comment_association": "OWNER"})


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


def new_commit(github, files=None, newer_diff=None):
    github["head"] = "def5678" + "0" * 33
    github["files"].update(files or {})
    github["newer_diff"] = newer_diff


NEWER = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 def total(items):
     result = sum(items)
+    # comment
     return result + 1
"""


def test_a_re_review_looks_only_at_whats_new(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])
    new_commit(github, newer_diff=NEWER + "diff --git a/vendored.py b/vendored.py\n--- a/vendored.py\n+++ b/vendored.py\n@@ -1 +1 @@\n-a\n+b\n")
    seen = []

    class Recording(FakeModel):
        async def review(self, instructions, diff_text):
            seen.append(diff_text)
            return await super().review(instructions, diff_text)
    monkeypatch.setattr(cli, "create_model", lambda *a, **k: Recording([]))

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    [reviewed] = seen
    assert "+ 3 |     # comment" in reviewed  # just the new commit's change
    assert "vendored.py" not in reviewed  # not a file the PR changes (a merge of the base, say)
    assert "Reviewed the changes since abc1234." in summary_of(github)


def test_after_a_force_push_the_whole_pr_is_reviewed(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])
    new_commit(github, newer_diff=None)  # the last reviewed commit isn't an ancestor any more

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert "Reviewed the changes since" not in summary_of(github)
    assert "1 open issue(s)" in summary_of(github)  # raised again: still one finding, not two


def test_a_re_review_only_raises_bugs_and_security_issues(capsys, monkeypatch, fake_model, github):
    fake_model([])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])
    new_commit(github, newer_diff=NEWER)
    fake_model([SUGGESTION.model_copy(update={"severity": "maintainability", "line": 2, "title": "Tidy"}),
                SUGGESTION.model_copy(update={"title": "A real bug"})])

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert "A real bug" in summary_of(github) and "Tidy" not in summary_of(github)
    assert "Left out 1 less important suggestion(s): re-reviews only raise bugs and security issues" in summary_of(github)


def test_a_fixed_issue_is_marked_addressed_and_its_conversation_resolved(capsys, monkeypatch, fake_model, github):
    fake_model([SUGGESTION])
    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])
    codemop_comment(github)  # the thread its comment started
    new_commit(github, files={"app.py": "def total(items):\n    result = sum(items)\n    return result\n"},
               newer_diff=NEWER)
    fake_model([])

    run(capsys, monkeypatch, ["review", "owner/repo#7", "--post"])

    assert "No issues found in these changes." in summary_of(github)
    assert "- ✅ 🐛 Bug `app.py:3`: Adds one to the total · addressed in def5678" in summary_of(github)
    assert github["resolved"] == ["thread-500"]


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


def test_only_files_in_keeps_the_prs_files():
    pr_diff = DIFF
    other = "diff --git a/other.py b/other.py\n--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n-a\n+b\n"

    assert cli.only_files_in(NEWER + other, pr_diff) == NEWER
