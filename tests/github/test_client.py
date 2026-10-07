import httpx
import pytest

from codemop.github.client import GitHubError, PullRequestRef, fetch_pr_diff, parse_pr_reference

PR = PullRequestRef("owner/repo", 7)


@pytest.mark.parametrize("text", [
    "owner/repo#7",
    " owner/repo#7 ",
    "https://github.com/owner/repo/pull/7",
    "https://github.com/owner/repo/pull/7/files",
    "https://github.example.com/owner/repo/pull/7?w=1",
])
def test_parses_pr_references(text):
    assert parse_pr_reference(text) == PR


@pytest.mark.parametrize("text", ["owner/repo", "repo#7", "https://github.com/owner/repo/issues/7", "owner/repo#x"])
def test_rejects_things_that_arent_prs(text):
    with pytest.raises(ValueError, match="Not a pull request"):
        parse_pr_reference(text)


def api(status=200, body="diff --git a/x b/x\n"):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, text=body)
    return httpx.MockTransport(handler), requests


@pytest.mark.asyncio
async def test_fetches_the_diff_with_the_token():
    transport, requests = api()

    diff = await fetch_pr_diff(PR, token="ghp_x", transport=transport)

    assert diff.startswith("diff --git")
    [request] = requests
    assert str(request.url) == "https://api.github.com/repos/owner/repo/pulls/7"
    assert request.headers["Accept"] == "application/vnd.github.diff"
    assert request.headers["Authorization"] == "Bearer ghp_x"


@pytest.mark.asyncio
async def test_no_token_no_authorization_header():
    transport, requests = api()

    await fetch_pr_diff(PR, transport=transport)

    assert "Authorization" not in requests[0].headers


@pytest.mark.asyncio
@pytest.mark.parametrize("status, body, token, expected", [
    (404, "", None, "if the repository is private, set GITHUB_TOKEN"),
    (404, "", "ghp_secret", "the token needs read access"),
    (401, "", "ghp_secret", "rejected the token"),
    (403, "API rate limit exceeded", None, "rate limit reached while fetching owner/repo#7; set GITHUB_TOKEN"),
    (406, "too many lines", None, "too large for the GitHub API"),
])
async def test_errors_say_what_to_do(status, body, token, expected):
    transport, _ = api(status, body)

    with pytest.raises(GitHubError) as error:
        await fetch_pr_diff(PR, token=token, transport=transport)

    assert expected in str(error.value)
    assert "ghp_secret" not in str(error.value)
