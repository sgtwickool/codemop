"""
The codemop command, with a fake model and a fake GitHub.
"""
import io
import json

import pytest

from codemop import cli
from codemop.github.client import GitHubError
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
