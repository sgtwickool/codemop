"""Changing a repository on GitHub: committing files, commit statuses, and who may write."""
from typing import Dict, Optional

import httpx

from codemop.github.client import (
    DEFAULT_API_URL, JSON, GitHubError, _request,
)


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
STATUS_CONTEXT = "CodeMop"
async def set_commit_status(
    repo: str,
    sha: str,
    state: str,
    description: str,
    *,
    target_url: Optional[str] = None,
    token: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> None:
    """Set CodeMop's commit status (pending, success, failure or error), which branch protection can require"""
    url = f"{api_url.rstrip('/')}/repos/{repo}/statuses/{sha}"
    body = {"state": state, "context": STATUS_CONTEXT, "description": description[:140]}
    if target_url:
        body["target_url"] = target_url
    response = await _request("POST", url, JSON, token, transport, json=body)
    if response.status_code != 201:
        hint = ": the token needs statuses: write" if response.status_code in (403, 404) else ""
        raise GitHubError(f"GitHub returned {response.status_code} setting the CodeMop status on {sha[:7]}{hint}",
                          response.status_code)
