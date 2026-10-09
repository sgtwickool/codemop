"""A pull request on GitHub: its diff, its head commit, and the repository's files and history."""
import io
import tarfile
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx

from codemop.github.client import (
    DEFAULT_API_URL, JSON, GitHubError, PullRequestRef, _error_message, _request, headers,
)

MAX_SNAPSHOT_BYTES = 30_000_000  # the most downloaded for a repository's snapshot (compressed)
MAX_SNAPSHOT_UNPACKED = 300_000_000  # and the most unpacked from it, so a small download can't be a huge one
MAX_SNAPSHOT_FILE = 500_000  # larger files aren't the code a review needs


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


async def fetch_snapshot(
    repo: str,
    ref: str,
    *,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Optional[Dict[str, str]]:
    """
    The repository's text files at `ref` (path: text), from one download of its tarball; None
    if it's too large or can't be downloaded. Kept in memory: nothing is written to disk, so
    nothing in it can be run, even from a fork's pull request.
    """
    url = f"{api_url.rstrip('/')}/repos/{repo}/tarball/{ref}"
    data = bytearray()
    # GitHub redirects to a download link (without the token, which httpx drops on the way)
    async with httpx.AsyncClient(headers=headers(JSON, token), timeout=120.0, transport=transport,
                                 follow_redirects=True) as client:
        try:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    return None
                async for chunk in response.aiter_bytes():
                    data += chunk
                    if len(data) > MAX_SNAPSHOT_BYTES:
                        return None
        except httpx.HTTPError:
            return None
    return _text_files(bytes(data))


def _text_files(tarball: bytes) -> Optional[Dict[str, str]]:
    """The text files in a repository's tarball, without the top-level folder GitHub puts them in"""
    files, unpacked = {}, 0
    try:
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
            for member in archive:
                unpacked += member.size
                if unpacked > MAX_SNAPSHOT_UNPACKED:
                    return None
                if not member.isfile() or member.size > MAX_SNAPSHOT_FILE or "/" not in member.name:
                    continue
                content = archive.extractfile(member).read()
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    continue  # not text
                if "\0" not in text:
                    files[member.name.split("/", 1)[1]] = text
    except (tarfile.TarError, EOFError, OSError):
        return None
    return files
