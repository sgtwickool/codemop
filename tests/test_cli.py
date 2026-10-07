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

    def __init__(self, result):
        self.result = result

    async def review(self, instructions, diff_text):
        if isinstance(self.result, Exception):
            raise self.result
        return ModelReview(suggestions=self.result), Usage(input_tokens=1234, output_tokens=56)


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
    assert "1 suggestion(s) · 1 chunk(s) · 1,234 input / 56 output tokens" in out


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
