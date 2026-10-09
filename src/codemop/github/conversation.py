"""A pull request's conversation on GitHub: comments, reviews, review threads and reactions."""
from dataclasses import dataclass
from typing import List, Optional

import httpx

from codemop.github.client import (
    DEFAULT_API_URL, JSON, GitHubError, PullRequestRef, _error_message, _request,
)


# A PR's conversation can be long; CodeMop's summary may be anywhere in it
MAX_COMMENT_PAGES = 10
def _write_error(response: httpx.Response, pr: PullRequestRef, token: Optional[str], doing: str) -> GitHubError:
    status = response.status_code
    if status in (401, 403, 404):
        hint = ("the token needs write access to pull requests (pull-requests: write)" if token
                else "posting needs a token: set GITHUB_TOKEN (or log in with `gh auth login`)")
        return GitHubError(f"GitHub returned {status} {doing} on {pr}: {hint}", status)
    if status == 422:
        return GitHubError(f"GitHub rejected {doing.removeprefix('posting ')} for {pr}: {response.text[:300]}", status)
    return GitHubError(f"GitHub returned {status} {doing} on {pr}", status)
@dataclass(frozen=True)
class IssueComment:
    id: int
    body: str
    author: str
    author_is_bot: bool
    author_association: str  # OWNER, MEMBER, COLLABORATOR, CONTRIBUTOR, NONE...
async def list_issue_comments(
    pr: PullRequestRef,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> List[IssueComment]:
    """The PR's conversation comments, oldest first (up to MAX_COMMENT_PAGES pages of 100)"""
    url: Optional[str] = f"{api_url.rstrip('/')}/repos/{pr.repo}/issues/{pr.number}/comments?per_page=100"
    comments: List[IssueComment] = []
    for _ in range(MAX_COMMENT_PAGES):
        response = await _request("GET", url, JSON, token, transport)
        if response.status_code != 200:
            raise GitHubError(_error_message(response.status_code, response.text, pr, bool(token)), response.status_code)
        comments += [
            IssueComment(
                id=comment["id"],
                body=comment.get("body") or "",
                author=(comment.get("user") or {}).get("login", ""),
                author_is_bot=(comment.get("user") or {}).get("type") == "Bot",
                author_association=comment.get("author_association", "NONE"),
            )
            for comment in response.json()
        ]
        url = response.links.get("next", {}).get("url")
        if not url:
            break
    return comments
async def post_issue_comment(
    pr: PullRequestRef,
    body: str,
    *,
    comment_id: Optional[int] = None,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> str:
    """A new conversation comment on the PR, or with comment_id an edit of that one; its URL"""
    base = f"{api_url.rstrip('/')}/repos/{pr.repo}/issues"
    if comment_id is None:
        response = await _request("POST", f"{base}/{pr.number}/comments", JSON, token, transport, json={"body": body})
        ok = 201
    else:
        response = await _request("PATCH", f"{base}/comments/{comment_id}", JSON, token, transport, json={"body": body})
        ok = 200
    if response.status_code != ok:
        raise _write_error(response, pr, token, "posting the summary comment")
    return response.json().get("html_url", "")
async def post_review(
    pr: PullRequestRef,
    review: dict,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> str:
    """Post a pull request review (POST /repos/{owner}/{repo}/pulls/{number}/reviews); its URL"""
    url = f"{api_url.rstrip('/')}/repos/{pr.repo}/pulls/{pr.number}/reviews"
    response = await _request("POST", url, JSON, token, transport, json=review)
    if response.status_code == 200:
        return response.json().get("html_url", "")
    raise _write_error(response, pr, token, "posting the review")
@dataclass(frozen=True)
class ReviewThread:
    id: str  # GraphQL node id, for resolving it
    resolved: bool
    path: str
    line: Optional[int]
    first_comment_id: int
    first_comment_body: str
    first_comment_by_bot: bool
    first_comment_association: str  # OWNER, MEMBER, COLLABORATOR, CONTRIBUTOR, NONE...
_THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved path line
          comments(first: 1) { nodes { databaseId body authorAssociation author { __typename } } }
        }
      }
    }
  }
}
"""
async def _graphql(query: str, variables: dict, token: Optional[str], api_url: str,
                   transport: Optional[httpx.AsyncBaseTransport]) -> dict:
    # GitHub Enterprise Server serves GraphQL at /api/graphql next to /api/v3
    url = api_url.rstrip("/").removesuffix("/v3") + "/graphql"
    response = await _request("POST", url, JSON, token, transport, json={"query": query, "variables": variables})
    data = response.json() if response.status_code == 200 else {}
    if response.status_code != 200 or data.get("errors"):
        detail = "; ".join(e.get("message", "") for e in data.get("errors", [])) or str(response.status_code)
        raise GitHubError(f"GitHub's GraphQL API failed: {detail}", response.status_code)
    return data["data"]
async def list_review_threads(
    pr: PullRequestRef,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> List[ReviewThread]:
    """The PR's review threads (conversations on its code), with whether each is resolved"""
    owner, name = pr.repo.split("/")
    threads: List[ReviewThread] = []
    after = None
    for _ in range(MAX_COMMENT_PAGES):
        data = await _graphql(_THREADS_QUERY, {"owner": owner, "name": name, "number": pr.number, "after": after},
                              token, api_url, transport)
        page = data["repository"]["pullRequest"]["reviewThreads"]
        for node in page["nodes"]:
            first = (node["comments"]["nodes"] or [{}])[0]
            threads.append(ReviewThread(
                id=node["id"], resolved=node["isResolved"], path=node.get("path") or "", line=node.get("line"),
                first_comment_id=first.get("databaseId") or 0, first_comment_body=first.get("body") or "",
                first_comment_by_bot=(first.get("author") or {}).get("__typename") == "Bot",
                first_comment_association=first.get("authorAssociation") or "NONE",
            ))
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return threads
async def resolve_thread(
    thread_id: str,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> None:
    await _graphql("mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id } } }",
                   {"id": thread_id}, token, api_url, transport)
async def reply_to_review_comment(
    pr: PullRequestRef,
    comment_id: int,
    body: str,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> str:
    """Reply in the thread of a comment on the PR's code; the reply's URL"""
    url = f"{api_url.rstrip('/')}/repos/{pr.repo}/pulls/{pr.number}/comments/{comment_id}/replies"
    response = await _request("POST", url, JSON, token, transport, json={"body": body})
    if response.status_code != 201:
        raise _write_error(response, pr, token, "replying to a comment")
    return response.json().get("html_url", "")
@dataclass(frozen=True)
class ReviewComment:
    id: int
    body: str
    path: str
    line: Optional[int]
    in_reply_to: Optional[int]  # the first comment of its thread, for a reply
    author: str
    author_is_bot: bool
    author_association: str = "NONE"
async def fetch_review_comment(
    repo: str,
    comment_id: int,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Optional[ReviewComment]:
    """A comment on a pull request's code, or None if there's no such comment"""
    url = f"{api_url.rstrip('/')}/repos/{repo}/pulls/comments/{comment_id}"
    response = await _request("GET", url, JSON, token, transport)
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise GitHubError(f"GitHub returned {response.status_code} reading comment {comment_id} on {repo}",
                          response.status_code)
    data = response.json()
    user = data.get("user") or {}
    return ReviewComment(
        id=data["id"], body=data.get("body") or "", path=data.get("path") or "", line=data.get("line"),
        in_reply_to=data.get("in_reply_to_id"), author=user.get("login", ""), author_is_bot=user.get("type") == "Bot",
        author_association=data.get("author_association", "NONE"),
    )
async def react_to_issue_comment(
    repo: str,
    comment_id: int,
    reaction: str,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> None:
    """Add a reaction (+1, eyes, ...) to a comment in a PR's conversation; best effort"""
    url = f"{api_url.rstrip('/')}/repos/{repo}/issues/comments/{comment_id}/reactions"
    await _request("POST", url, JSON, token, transport, json={"content": reaction})
