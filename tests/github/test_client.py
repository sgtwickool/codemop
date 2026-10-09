import io
import json
import re
import tarfile

import httpx
import pytest

from codemop.github import pulls
from codemop.github.api import (
    GitHubError, PullRequestRef, commit_files, compare_commits, fetch_pr_diff, fetch_pull_request, fetch_repo_file,
    fetch_snapshot,
    list_issue_comments, list_review_threads, parse_pr_reference, post_issue_comment, post_review,
    reply_to_review_comment, resolve_thread, set_commit_status, user_permission,
)

PR = PullRequestRef("owner/repo", 7)


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    """Retries without waiting, in every test here"""
    monkeypatch.setattr("codemop.github.client.RETRY_DELAYS", [0, 0])


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
        {"id": 1, "body": "- [x] hi\r\n", "user": {"login": "github-actions[bot]", "type": "Bot"}, "author_association": "NONE"},
        {"id": 2, "body": None, "user": {"login": "sam", "type": "User"}, "author_association": "OWNER"},
    ]))

    comments = await list_issue_comments(PR, transport=transport)

    assert [(c.id, c.body, c.author_is_bot, c.author_association) for c in comments] == [
        (1, "- [x] hi\n", True, "NONE"), (2, "", False, "OWNER"),  # a box ticked on the web page comes back with \r\n
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


@pytest.mark.asyncio
async def test_reads_a_file_at_a_commit():
    transport, requests = api(body="x = 1\n")

    assert await fetch_repo_file("owner/repo", "app.py", ref="abc", transport=transport) == "x = 1\n"
    assert str(requests[0].url) == "https://api.github.com/repos/owner/repo/contents/app.py?ref=abc"


@pytest.mark.asyncio
@pytest.mark.parametrize("status, body, expected", [(200, {"permission": "write"}, "write"), (404, {}, "none")])
async def test_reads_a_users_permission(status, body, expected):
    transport, requests = json_api((status, body))

    assert await user_permission("owner/repo", "sam", transport=transport) == expected
    assert str(requests[0].url) == "https://api.github.com/repos/owner/repo/collaborators/sam/permission"


@pytest.mark.asyncio
async def test_commits_files_as_one_commit_and_moves_the_branch():
    transport, requests = json_api(
        (200, {"tree": {"sha": "tree0"}}),
        (200, {"tree": [{"path": "run.sh", "mode": "100755"}, {"path": "app.py", "mode": "100644"}]}),
        (201, {"sha": "tree1"}),
        (201, {"sha": "commit1"}),
        (200, {"object": {"sha": "commit1"}}),
    )

    sha = await commit_files("owner/repo", "feature", "parent0", {"run.sh": "echo hi\n", "new.py": "x\n"}, "msg",
                             token="ghp_x", transport=transport)

    assert sha == "commit1"
    get_commit, get_tree, post_tree, post_commit, patch_ref = requests
    assert str(get_tree.url).endswith("/git/trees/tree0")  # just the directory the files are in
    assert json.loads(post_tree.content) == {"base_tree": "tree0", "tree": [
        {"path": "run.sh", "mode": "100755", "type": "blob", "content": "echo hi\n"},  # stays executable
        {"path": "new.py", "mode": "100644", "type": "blob", "content": "x\n"},
    ]}
    assert json.loads(post_commit.content) == {"message": "msg", "tree": "tree1", "parents": ["parent0"]}
    assert (patch_ref.method, str(patch_ref.url)) == ("PATCH", "https://api.github.com/repos/owner/repo/git/refs/heads/feature")
    assert json.loads(patch_ref.content) == {"sha": "commit1", "force": False}


@pytest.mark.asyncio
async def test_commit_modes_come_from_just_the_directories_changed():
    """Not the whole repository's tree, which can be huge (and is cut short past 100,000 entries)"""
    transport, requests = json_api(
        (200, {"tree": {"sha": "tree0"}}),
        (200, {"tree": [{"path": "run.sh", "mode": "100755"}]}),
        (404, {"message": "Not Found"}),  # a directory the commit creates
        (201, {"sha": "tree1"}), (201, {"sha": "commit1"}), (200, {}),
    )

    await commit_files("owner/repo", "feature", "parent0", {"bin/run.sh": "echo hi\n", "new/a.py": "x\n"}, "msg",
                       transport=transport)

    assert [str(r.url).split("/git/")[1] for r in requests[1:3]] == ["trees/parent0:bin", "trees/parent0:new"]
    assert [entry["mode"] for entry in json.loads(requests[3].content)["tree"]] == ["100755", "100644"]


@pytest.mark.asyncio
async def test_committing_when_the_branch_has_moved_is_a_422():
    transport, _ = json_api((200, {"tree": {"sha": "t"}}), (200, {"tree": []}), (201, {"sha": "t1"}),
                            (201, {"sha": "c1"}), (422, {"message": "Update is not a fast forward"}))

    with pytest.raises(GitHubError) as error:
        await commit_files("owner/repo", "feature", "p", {"a": "b"}, "m", transport=transport)
    assert error.value.status == 422




@pytest.mark.asyncio
async def test_a_brief_github_failure_is_retried():
    """Seen on PR #5: GitHub returned a 500 for a diff that came back fine a second later"""
    transport, requests = json_api((500, {}), (502, {}), (200, {"head": {"sha": "abc"}, "state": "open"}))

    assert (await fetch_pull_request(PR, transport=transport)).head_sha == "abc"
    assert len(requests) == 3


@pytest.mark.asyncio
async def test_retries_give_up_after_two():
    transport, requests = json_api((500, {}), (500, {}), (500, {}))

    with pytest.raises(GitHubError) as error:
        await fetch_pull_request(PR, transport=transport)
    assert error.value.status == 500
    assert len(requests) == 3


@pytest.mark.asyncio
async def test_creating_something_isnt_retried():
    """The first attempt may have worked, and a second would post the review twice"""
    transport, requests = json_api((502, {}))

    with pytest.raises(GitHubError):
        await post_review(PR, {}, token="ghp_x", transport=transport)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_a_dropped_connection_is_retried():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("reset")
        return httpx.Response(200, text="diff --git a/x b/x\n")

    assert (await fetch_pr_diff(PR, transport=httpx.MockTransport(handler))).startswith("diff --git")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_lists_review_threads_page_by_page():
    def page(nodes, more):
        return (200, {"data": {"repository": {"pullRequest": {"reviewThreads": {
            "pageInfo": {"hasNextPage": more, "endCursor": "c1" if more else None}, "nodes": nodes}}}}})
    node = {"id": "T1", "isResolved": True, "path": "app.py", "line": 3,
            "comments": {"nodes": [{"databaseId": 9, "body": "b", "authorAssociation": "NONE", "author": {"__typename": "Bot"}}]}}
    transport, requests = json_api(page([node], True), page([{**node, "id": "T2", "isResolved": False}], False))

    threads = await list_review_threads(PR, transport=transport)

    assert [(t.id, t.resolved, t.path, t.line, t.first_comment_id, t.first_comment_by_bot) for t in threads] == [
        ("T1", True, "app.py", 3, 9, True), ("T2", False, "app.py", 3, 9, True),
    ]
    assert str(requests[0].url) == "https://api.github.com/graphql"
    assert json.loads(requests[1].content)["variables"]["after"] == "c1"


@pytest.mark.asyncio
async def test_graphql_errors_are_raised():
    transport, _ = json_api((200, {"errors": [{"message": "Resource not accessible by integration"}]}))

    with pytest.raises(GitHubError, match="Resource not accessible by integration"):
        await resolve_thread("T1", transport=transport)


@pytest.mark.asyncio
async def test_graphql_on_github_enterprise_server_is_next_to_the_rest_api():
    transport, requests = json_api((200, {"data": {}}))

    await resolve_thread("T1", api_url="https://github.example.com/api/v3", transport=transport)

    assert str(requests[0].url) == "https://github.example.com/api/graphql"


@pytest.mark.asyncio
async def test_replies_in_a_comments_thread():
    transport, requests = json_api((201, {"html_url": "https://github.com/r"}))

    await reply_to_review_comment(PR, 55, "Learned", token="ghp_x", transport=transport)

    assert str(requests[0].url) == "https://api.github.com/repos/owner/repo/pulls/7/comments/55/replies"
    assert json.loads(requests[0].content) == {"body": "Learned"}


@pytest.mark.asyncio
async def test_compares_commits_when_the_head_is_ahead():
    transport, requests = json_api((200, {"status": "ahead"}))
    diffs = []

    def handler(request):
        if request.headers["Accept"] == "application/vnd.github.diff":
            diffs.append(request)
            return httpx.Response(200, text="diff --git a/x b/x\n")
        return httpx.Response(200, json={"status": "ahead"})

    assert await compare_commits("owner/repo", "aaa", "bbb", transport=httpx.MockTransport(handler)) == "diff --git a/x b/x\n"
    assert str(diffs[0].url) == "https://api.github.com/repos/owner/repo/compare/aaa...bbb"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["diverged", "behind", "identical"])
async def test_no_diff_unless_the_head_is_ahead(status):
    """After a force-push the last reviewed commit isn't an ancestor: review the whole PR instead"""
    transport, requests = json_api((200, {"status": status}))

    assert await compare_commits("owner/repo", "aaa", "bbb", transport=transport) is None
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_sets_codemops_commit_status():
    transport, requests = json_api((201, {}))

    await set_commit_status("owner/repo", "abc", "failure", "x" * 200, target_url="https://github.com/s", token="t",
                            transport=transport)

    assert str(requests[0].url) == "https://api.github.com/repos/owner/repo/statuses/abc"
    body = json.loads(requests[0].content)
    assert (body["state"], body["context"], body["target_url"], len(body["description"])) == (
        "failure", "CodeMop", "https://github.com/s", 140)


@pytest.mark.asyncio
async def test_setting_a_status_without_permission_says_what_the_token_needs():
    transport, _ = json_api((403, {}))

    with pytest.raises(GitHubError, match="the token needs statuses: write"):
        await set_commit_status("owner/repo", "abc", "success", "ok", transport=transport)


def tarball(files, top="owner-repo-abc1234"):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, content in files.items():
            data = content if isinstance(content, bytes) else content.encode()
            info = tarfile.TarInfo(f"{top}/{path}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_a_snapshot_is_the_repositorys_text_files_from_one_download():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "api.github.com":  # GitHub redirects to the download
            return httpx.Response(302, headers={"Location": "https://codeload.github.com/owner/repo/tar.gz/abc"})
        return httpx.Response(200, content=tarball({"app.py": "x = 1\n", "logo.png": b"\x89PNG\x00\xff",
                                                    "big.txt": "a" * 600_000}))

    files = await fetch_snapshot("owner/repo", "abc", token="ghp_x", transport=httpx.MockTransport(handler))

    assert files == {"app.py": "x = 1\n"}  # not binary files or large ones
    assert str(requests[0].url) == "https://api.github.com/repos/owner/repo/tarball/abc"
    assert "authorization" not in requests[1].headers  # the token stays with GitHub's API


@pytest.mark.asyncio
async def test_no_snapshot_when_its_too_large_or_cant_be_downloaded(monkeypatch):
    big = tarball({"a.py": "x = 1\n" * 1000})
    monkeypatch.setattr(pulls, "MAX_SNAPSHOT_BYTES", len(big) - 1)
    for response in (httpx.Response(200, content=big), httpx.Response(404), httpx.Response(200, content=b"not a tarball")):
        assert await fetch_snapshot("owner/repo", "abc", transport=httpx.MockTransport(lambda r: response)) is None
