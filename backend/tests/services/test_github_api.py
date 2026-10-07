"""
Tests for fetching PR diffs from the GitHub REST API.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.github import GitHubAPIError, fetch_pr_diff


def http_error(status: int, body: str = "") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.github.com/repos/o/r/pulls/1")
    return httpx.HTTPStatusError("error", request=request, response=httpx.Response(status, text=body, request=request))


@pytest.fixture
def github(monkeypatch):
    """fetch_with_retry as used by the GitHub service, returning a diff by default."""
    from app.config import settings
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
    monkeypatch.setattr(settings, "GITHUB_API_URL", "https://api.github.com")
    mock = AsyncMock(return_value=MagicMock(text="diff --git a/app.py b/app.py\n"))
    with patch("app.utils.http.fetch_with_retry", new=mock):
        yield mock


@pytest.mark.asyncio
async def test_fetches_the_diff_from_the_rest_api(github):
    diff = await fetch_pr_diff("owner/repo", 7)

    assert diff.startswith("diff --git")
    url, method = github.call_args.args
    assert url == "https://api.github.com/repos/owner/repo/pulls/7"
    assert method == "GET"
    assert github.call_args.kwargs["headers"]["Accept"] == "application/vnd.github.diff"


@pytest.mark.asyncio
async def test_no_token_means_no_authorization_header(github):
    await fetch_pr_diff("owner/repo", 7)

    assert "Authorization" not in github.call_args.kwargs["headers"]


@pytest.mark.asyncio
async def test_token_is_sent_when_configured(github, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_test")

    await fetch_pr_diff("owner/repo", 7)

    assert github.call_args.kwargs["headers"]["Authorization"] == "Bearer ghp_test"


@pytest.mark.asyncio
async def test_enterprise_api_url_is_used(github, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "GITHUB_API_URL", "https://github.example.com/api/v3/")

    await fetch_pr_diff("owner/repo", 7)

    assert github.call_args.args[0] == "https://github.example.com/api/v3/repos/owner/repo/pulls/7"


@pytest.mark.asyncio
@pytest.mark.parametrize("status, body, token, expected", [
    (404, "", "", "if the repository is private, set GITHUB_TOKEN"),
    (404, "", "ghp_test", "GITHUB_TOKEN needs read access"),
    (401, "", "ghp_test", "rejected GITHUB_TOKEN"),
    (403, "API rate limit exceeded", "", "rate limit reached while fetching owner/repo#7; set GITHUB_TOKEN"),
    (403, "API rate limit exceeded", "ghp_test", "rate limit reached while fetching owner/repo#7"),
    (406, "diff exceeded the maximum number of lines", "", "too large for the GitHub API"),
    (500, "", "", "GitHub returned 500"),
])
async def test_errors_say_what_to_do(github, monkeypatch, status, body, token, expected):
    from app.config import settings
    monkeypatch.setattr(settings, "GITHUB_TOKEN", token)
    github.side_effect = http_error(status, body)

    with pytest.raises(GitHubAPIError) as error:
        await fetch_pr_diff("owner/repo", 7)

    assert expected in str(error.value)
    if token:
        assert "set GITHUB_TOKEN" not in str(error.value)


@pytest.mark.asyncio
async def test_token_never_appears_in_error_messages(github, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_secret_value")
    github.side_effect = http_error(401)

    with pytest.raises(GitHubAPIError) as error:
        await fetch_pr_diff("owner/repo", 7)

    assert "ghp_secret_value" not in str(error.value)
