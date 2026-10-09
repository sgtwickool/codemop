"""A pull request on GitHub: its diff, its head commit, and the repository's files and history."""
from dataclasses import dataclass
from typing import List, Optional

import httpx

from codemop.github.client import (
    DEFAULT_API_URL, JSON, GitHubError, PullRequestRef, _error_message, _request,
)


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
async def list_paths(
    repo: str,
    ref: str,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> List[str]:
    """The paths of the files in the repository at `ref` (GitHub may cut a very large tree short)"""
    url = f"{api_url.rstrip('/')}/repos/{repo}/git/trees/{ref}?recursive=1"
    response = await _request("GET", url, JSON, token, transport)
    if response.status_code != 200:
        raise GitHubError(f"GitHub returned {response.status_code} listing the files in {repo}", response.status_code)
    return [entry["path"] for entry in response.json().get("tree", []) if entry.get("type") == "blob"]
