"""
The codemop command, with a fake model and a fake GitHub.
"""
import io
import json

import pytest

from codemop import cli
from codemop.github.client import GitHubError, IssueComment, PullRequest
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
    monkeypatch.setattr(cli, "fetch_repo_file", fake_fetch_repo_file)
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
    }

    async def fetch_pull_request(pr, token=None, api_url=None):
        return PullRequest(head_sha=state["head"], state="open", draft=False, head_ref="feature",
                           head_repo=state["head_repo"])

    async def fetch_repo_file(repo, path, ref=None, token=None, api_url=None):
        return state["files"].get(path) if ref else None  # no .codemop.yml on the default branch

    async def user_permission(repo, user, token=None, api_url=None):
        return state["permissions"].get(user, "none")

    async def commit_files(repo, branch, parent_sha, files, message, token=None, api_url=None):
        if state["branch_moves"]:
            state["branch_moves"] -= 1
            state["head"] = "moved00" + "0" * 33
            raise GitHubError("the branch moved", 422)
        assert (repo, branch, parent_sha) == (state["head_repo"], "feature", state["head"])
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
                       ("user_permission", user_permission), ("commit_files", commit_files)]:
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
    assert "Found 1 issue(s) ([comments on the code](https://github.com/owner/repo/pull/7#pullrequestreview-1))" in summary_of(github)
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
    assert "No issues found." in summary_of(github)
    assert len(github["reviews"]) == 1  # no inline comments, so no second review


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
    assert "<!-- codemop-fixes: " in summary_of(github)


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
