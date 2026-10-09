"""
The GitHub REST API: fetching pull request diffs and files, and posting reviews.

Uses a token when one is given, which private repositories need (and which raises the
rate limit from 60 to 5,000 requests an hour for public ones). Posting needs one with
write access to pull requests.
"""
import asyncio
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx

DEFAULT_API_URL = "https://api.github.com"

_PR_REFERENCE = re.compile(r"^(?P<repo>[\w.-]+/[\w.-]+)#(?P<number>\d+)$")
_PR_URL = re.compile(r"^https?://[^/]+/(?P<repo>[\w.-]+/[\w.-]+)/pull/(?P<number>\d+)(?:[/?#].*)?$")


JSON = "application/vnd.github+json"
# A PR's conversation can be long; CodeMop's summary may be anywhere in it
MAX_COMMENT_PAGES = 10

# GitHub sometimes fails a request briefly (a 500 fetching a diff that works a second later).
# Requests that are safe to repeat are tried again; creating something isn't, since the first
# attempt may have worked
RETRY_STATUSES = {500, 502, 503, 504}
RETRY_METHODS = {"GET", "PATCH", "PUT", "DELETE"}
RETRY_DELAYS = [1.0, 3.0]


class GitHubError(Exception):
    """A GitHub request failed; the message says what to do about it"""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class PullRequestRef:
    repo: str  # owner/name
    number: int

    def __str__(self) -> str:
        return f"{self.repo}#{self.number}"


def parse_pr_reference(text: str) -> PullRequestRef:
    """owner/repo#123, or a PR URL like https://github.com/owner/repo/pull/123"""
    match = _PR_REFERENCE.match(text.strip()) or _PR_URL.match(text.strip())
    if not match:
        raise ValueError(f"Not a pull request: {text!r} (use owner/repo#123 or a PR URL)")
    return PullRequestRef(match.group("repo"), int(match.group("number")))


def _error_message(status: int, body: str, pr: PullRequestRef, has_token: bool) -> str:
    if status == 401:
        return f"GitHub rejected the token while fetching {pr}; check it's valid and hasn't expired"
    if status == 403 and "rate limit" in body.lower():
        hint = "" if has_token else "; set GITHUB_TOKEN (or log in with `gh auth login`) for a higher limit"
        return f"GitHub API rate limit reached while fetching {pr}{hint}"
    if status in (403, 404):
        if has_token:
            return (f"GitHub returned {status} for {pr}: the token needs read access to this "
                    "repository's pull requests and contents")
        return (f"GitHub returned {status} for {pr}: if the repository is private, set "
                "GITHUB_TOKEN (or log in with `gh auth login`)")
    if status == 406:
        return f"The diff for {pr} is too large for the GitHub API to return"
    return f"GitHub returned {status} while fetching the diff for {pr}"


async def _request(
    method: str,
    url: str,
    accept: str,
    token: Optional[str],
    transport: Optional[httpx.AsyncBaseTransport],
    json: Optional[dict] = None,
) -> httpx.Response:
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    retries = RETRY_DELAYS if method in RETRY_METHODS else []
    async with httpx.AsyncClient(headers=headers, timeout=60.0, transport=transport) as client:
        for attempt in range(len(retries) + 1):
            try:
                response = await client.request(method, url, json=json)
            except httpx.TransportError:
                if attempt == len(retries):
                    raise GitHubError(f"Couldn't connect to {url.split('/repos/')[0]}; check the network")
            else:
                if response.status_code not in RETRY_STATUSES or attempt == len(retries):
                    return response
            await asyncio.sleep(retries[attempt])


async def fetch_pr_diff(
    pr: PullRequestRef,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> str:
    """The PR's diff, from GET /repos/{owner}/{repo}/pulls/{number} as application/vnd.github.diff"""
    url = f"{api_url.rstrip('/')}/repos/{pr.repo}/pulls/{pr.number}"
    response = await _request("GET", url, "application/vnd.github.diff", token, transport)
    if response.status_code != 200:
        raise GitHubError(_error_message(response.status_code, response.text, pr, bool(token)))
    return response.text


async def fetch_repo_file(
    repo: str,
    path: str,
    *,
    ref: Optional[str] = None,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Optional[str]:
    """
    A file's contents at `ref`, by default on the repository's default branch, or None if
    there's no such file.

    (Settings come from the default branch, not the PR's: a pull request mustn't be able to
    change how it's reviewed.) A 404 also covers a private repository read without access;
    fetching its diff reports that properly.
    """
    url = f"{api_url.rstrip('/')}/repos/{repo}/contents/{path}" + (f"?ref={ref}" if ref else "")
    response = await _request("GET", url, "application/vnd.github.raw+json", token, transport)
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise GitHubError(f"GitHub returned {response.status_code} reading {path} from {repo}")
    return response.text


@dataclass(frozen=True)
class PullRequest:
    head_sha: str  # the commit a review's line numbers refer to
    state: str  # open or closed
    draft: bool
    head_ref: str = ""  # the PR's branch
    head_repo: str = ""  # where that branch is: a fork's, for a PR from a fork


async def fetch_pull_request(
    pr: PullRequestRef,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> PullRequest:
    url = f"{api_url.rstrip('/')}/repos/{pr.repo}/pulls/{pr.number}"
    response = await _request("GET", url, JSON, token, transport)
    if response.status_code != 200:
        raise GitHubError(_error_message(response.status_code, response.text, pr, bool(token)), response.status_code)
    data = response.json()
    return PullRequest(
        head_sha=data["head"]["sha"], state=data["state"], draft=bool(data.get("draft")),
        head_ref=data["head"].get("ref", ""), head_repo=((data["head"].get("repo") or {}).get("full_name") or ""),
    )


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


def _write_error(response: httpx.Response, pr: PullRequestRef, token: Optional[str], doing: str) -> GitHubError:
    status = response.status_code
    if status in (401, 403, 404):
        hint = ("the token needs write access to pull requests (pull-requests: write)" if token
                else "posting needs a token: set GITHUB_TOKEN (or log in with `gh auth login`)")
        return GitHubError(f"GitHub returned {status} {doing} on {pr}: {hint}", status)
    if status == 422:
        return GitHubError(f"GitHub rejected {doing.removeprefix('posting ')} for {pr}: {response.text[:300]}", status)
    return GitHubError(f"GitHub returned {status} {doing} on {pr}", status)


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


async def user_permission(
    repo: str,
    user: str,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> str:
    """A user's permission on the repository: admin, maintain, write, triage, read or none"""
    url = f"{api_url.rstrip('/')}/repos/{repo}/collaborators/{user}/permission"
    response = await _request("GET", url, JSON, token, transport)
    if response.status_code == 404:
        return "none"
    if response.status_code != 200:
        raise GitHubError(f"GitHub returned {response.status_code} checking {user}'s permission on {repo}",
                          response.status_code)
    return response.json().get("permission", "none")


async def commit_files(
    repo: str,
    branch: str,
    parent_sha: str,
    files: Dict[str, str],
    message: str,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> str:
    """
    Commit new contents for `files` (path: text) on top of `parent_sha` as one commit, and
    move `branch` to it; the new commit's sha. Through the API, so nothing is checked out.
    Fails (status 422) if the branch has moved on from parent_sha meanwhile.
    """
    base = f"{api_url.rstrip('/')}/repos/{repo}/git"

    async def call(method: str, path: str, body: Optional[dict] = None) -> dict:
        response = await _request(method, f"{base}/{path}", JSON, token, transport, json=body)
        if response.status_code not in (200, 201):
            hint = (": the token needs write access to contents (contents: write)"
                    if response.status_code in (403, 404) else "")
            raise GitHubError(f"GitHub returned {response.status_code} committing to {repo}{hint}", response.status_code)
        return response.json()

    tree_sha = (await call("GET", f"commits/{parent_sha}"))["tree"]["sha"]
    # Keep each file's mode (an executable script stays executable)
    modes = {entry["path"]: entry["mode"] for entry in (await call("GET", f"trees/{tree_sha}?recursive=1"))["tree"]}
    tree = await call("POST", "trees", {
        "base_tree": tree_sha,
        "tree": [{"path": path, "mode": modes.get(path, "100644"), "type": "blob", "content": text}
                 for path, text in files.items()],
    })
    commit = await call("POST", "commits", {"message": message, "tree": tree["sha"], "parents": [parent_sha]})
    await call("PATCH", f"refs/heads/{branch}", {"sha": commit["sha"], "force": False})
    return commit["sha"]


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


async def compare_commits(
    repo: str,
    base: str,
    head: str,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Optional[str]:
    """
    The diff from `base` to `head` if head is ahead of base (base is one of its ancestors), as
    after an ordinary push; None otherwise (a force-push or rebase), or if GitHub can't say
    """
    url = f"{api_url.rstrip('/')}/repos/{repo}/compare/{base}...{head}"
    status = await _request("GET", url + "?per_page=1", JSON, token, transport)
    if status.status_code != 200 or status.json().get("status") != "ahead":
        return None
    response = await _request("GET", url, "application/vnd.github.diff", token, transport)
    return response.text if response.status_code == 200 else None
