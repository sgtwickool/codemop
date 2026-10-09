"""
The GitHub REST API: fetching pull request diffs and files, and posting reviews.

Uses a token when one is given, which private repositories need (and which raises the
rate limit from 60 to 5,000 requests an hour for public ones). Posting needs one with
write access to pull requests.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

import httpx

DEFAULT_API_URL = "https://api.github.com"

_PR_REFERENCE = re.compile(r"^(?P<repo>[\w.-]+/[\w.-]+)#(?P<number>\d+)$")
_PR_URL = re.compile(r"^https?://[^/]+/(?P<repo>[\w.-]+/[\w.-]+)/pull/(?P<number>\d+)(?:[/?#].*)?$")


JSON = "application/vnd.github+json"


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
    async with httpx.AsyncClient(headers=headers, timeout=60.0, transport=transport) as client:
        try:
            return await client.request(method, url, json=json)
        except httpx.TransportError:
            raise GitHubError(f"Couldn't connect to {url.split('/repos/')[0]}; check the network")


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
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Optional[str]:
    """
    A file's contents on the repository's default branch, or None if there's no such file.

    (The default branch, not the PR's: a pull request mustn't be able to change how it's
    reviewed.) A 404 also covers a private repository read without access; fetching its diff
    reports that properly.
    """
    url = f"{api_url.rstrip('/')}/repos/{repo}/contents/{path}"
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
    return PullRequest(head_sha=data["head"]["sha"], state=data["state"], draft=bool(data.get("draft")))


async def fetch_review_bodies(
    pr: PullRequestRef,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> List[tuple[str, str]]:
    """(commit_id, body) of the PR's reviews, oldest first (the first 100)"""
    url = f"{api_url.rstrip('/')}/repos/{pr.repo}/pulls/{pr.number}/reviews?per_page=100"
    response = await _request("GET", url, JSON, token, transport)
    if response.status_code != 200:
        raise GitHubError(_error_message(response.status_code, response.text, pr, bool(token)), response.status_code)
    return [(review.get("commit_id") or "", review.get("body") or "") for review in response.json()]


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
    if response.status_code in (401, 403, 404):
        hint = ("the token needs write access to pull requests (pull-requests: write)" if token
                else "posting needs a token: set GITHUB_TOKEN (or log in with `gh auth login`)")
        raise GitHubError(f"GitHub returned {response.status_code} posting the review on {pr}: {hint}",
                          response.status_code)
    if response.status_code == 422:
        raise GitHubError(f"GitHub rejected the review for {pr}: {response.text[:300]}", 422)
    raise GitHubError(f"GitHub returned {response.status_code} posting the review on {pr}", response.status_code)
