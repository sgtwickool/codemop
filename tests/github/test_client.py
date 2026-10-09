import json
import re

import httpx
import pytest

from codemop.github.client import (
    GitHubError, PullRequestRef, fetch_pr_diff, fetch_pull_request, fetch_repo_file, list_issue_comments,
    parse_pr_reference, post_issue_comment, post_review,
)

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


@pytest.mark.asyncio
async def test_reads_a_file_from_the_default_branch():
    transport, requests = api(body="min_confidence: 0.7\n")

    text = await fetch_repo_file("owner/repo", ".codemop.yml", token="t", transport=transport)

    assert text == "min_confidence: 0.7\n"
    [request] = requests
    assert str(request.url) == "https://api.github.com/repos/owner/repo/contents/.codemop.yml"  # no ref: default branch
    assert request.headers["Accept"] == "application/vnd.github.raw+json"


@pytest.mark.asyncio
async def test_a_missing_file_is_none():
    transport, _ = api(404, "Not Found")

    assert await fetch_repo_file("owner/repo", ".codemop.yml", transport=transport) is None


@pytest.mark.asyncio
async def test_other_errors_reading_a_file_are_raised():
    transport, _ = api(500, "oops")

    with pytest.raises(GitHubError, match="GitHub returned 500 reading .codemop.yml from owner/repo"):
        await fetch_repo_file("owner/repo", ".codemop.yml", transport=transport)


def json_api(*responses):
    """Answers requests in turn with (status, JSON) pairs"""
    requests = []
    queue = list(responses)

    def handler(request):
        requests.append(request)
        status, body = queue.pop(0)
        return httpx.Response(status, json=body)
    return httpx.MockTransport(handler), requests


@pytest.mark.asyncio
async def test_fetches_the_pull_requests_head_commit():
    transport, requests = json_api((200, {"head": {"sha": "abc"}, "state": "open", "draft": False}))

    pr = await fetch_pull_request(PR, token="ghp_x", transport=transport)

    assert (pr.head_sha, pr.state, pr.draft) == ("abc", "open", False)
    assert requests[0].headers["Accept"] == "application/vnd.github+json"


@pytest.mark.asyncio
async def test_lists_the_prs_comments_with_their_authors():
    transport, requests = json_api((200, [
        {"id": 1, "body": "hi", "user": {"login": "github-actions[bot]", "type": "Bot"}, "author_association": "NONE"},
        {"id": 2, "body": None, "user": {"login": "sam", "type": "User"}, "author_association": "OWNER"},
    ]))

    comments = await list_issue_comments(PR, transport=transport)

    assert [(c.id, c.body, c.author_is_bot, c.author_association) for c in comments] == [
        (1, "hi", True, "NONE"), (2, "", False, "OWNER"),
    ]
    assert str(requests[0].url) == "https://api.github.com/repos/owner/repo/issues/7/comments?per_page=100"


@pytest.mark.asyncio
async def test_reads_every_page_of_comments():
    """A busy PR has more than 100 comments, and the summary may be after the first page"""
    requests = []

    def handler(request):
        requests.append(request)
        page = int(request.url.params.get("page", 1))
        headers = {"Link": f'<https://api.github.com/repos/owner/repo/issues/7/comments?per_page=100&page={page + 1}>; rel="next"'} if page < 3 else {}
        return httpx.Response(200, headers=headers, json=[{"id": page, "body": f"page {page}", "user": {"login": "a"}}])

    comments = await list_issue_comments(PR, transport=httpx.MockTransport(handler))

    assert [c.id for c in comments] == [1, 2, 3]
    assert len(requests) == 3


@pytest.mark.asyncio
async def test_posts_a_new_comment_or_edits_an_existing_one():
    transport, requests = json_api((201, {"html_url": "https://github.com/c/1"}), (200, {"html_url": "https://github.com/c/1"}))

    await post_issue_comment(PR, "first", token="ghp_x", transport=transport)
    await post_issue_comment(PR, "second", comment_id=99, token="ghp_x", transport=transport)

    new, edit = requests
    assert (new.method, str(new.url)) == ("POST", "https://api.github.com/repos/owner/repo/issues/7/comments")
    assert (edit.method, str(edit.url)) == ("PATCH", "https://api.github.com/repos/owner/repo/issues/comments/99")
    assert json.loads(edit.content) == {"body": "second"}


@pytest.mark.asyncio
async def test_posts_a_review():
    transport, requests = json_api((200, {"html_url": "https://github.com/owner/repo/pull/7#pullrequestreview-1"}))
    review = {"commit_id": "abc", "event": "COMMENT", "body": "b", "comments": []}

    url = await post_review(PR, review, token="ghp_x", transport=transport)

    assert url.endswith("#pullrequestreview-1")
    [request] = requests
    assert request.method == "POST"
    assert str(request.url) == "https://api.github.com/repos/owner/repo/pulls/7/reviews"
    assert json.loads(request.content) == review


@pytest.mark.asyncio
@pytest.mark.parametrize("status, token, expected", [
    (403, "ghp_x", "the token needs write access to pull requests (pull-requests: write)"),
    (401, None, "posting needs a token"),
    (422, "ghp_x", "GitHub rejected the review for owner/repo#7"),
])
async def test_posting_errors_say_what_to_do(status, token, expected):
    transport, _ = json_api((status, {"message": "nope"}))

    with pytest.raises(GitHubError, match=re.escape(expected)) as error:
        await post_review(PR, {}, token=token, transport=transport)
    assert error.value.status == status
