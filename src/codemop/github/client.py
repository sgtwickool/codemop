"""
The GitHub API's plumbing: requests (with retries for brief failures), errors that say what
to do, and pull request references. The calls themselves are in pulls, conversation and
commits; codemop.github.api gathers them in one place.

Uses a token when one is given, which private repositories need (and which raises the
rate limit from 60 to 5,000 requests an hour for public ones). Posting needs one with
write access to pull requests.
"""
import asyncio
import re
from dataclasses import dataclass
from typing import Optional
import httpx
DEFAULT_API_URL = "https://api.github.com"
_PR_REFERENCE = re.compile(r"^(?P<repo>[\w.-]+/[\w.-]+)#(?P<number>\d+)$")
_PR_URL = re.compile(r"^https?://[^/]+/(?P<repo>[\w.-]+/[\w.-]+)/pull/(?P<number>\d+)(?:[/?#].*)?$")
JSON = "application/vnd.github+json"
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
