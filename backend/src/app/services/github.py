import hmac
import json
import hashlib
from fastapi import HTTPException, Header
from typing import Optional, Dict, Any
import logging
import httpx
from app.config import settings
from app.utils.http import fetch_with_retry

logger = logging.getLogger(__name__)

async def validate_github_webhook_signature(
    request_body: bytes,
    x_hub_signature_256: Optional[str] = Header(None)
) -> None:
    """Validate GitHub webhook signature"""
    if not settings.GITHUB_WEBHOOK_SECRET:
        # Only allowed for local development; startup refuses this anywhere else
        if settings.is_development:
            return
        raise HTTPException(status_code=503, detail="Webhook secret is not configured")

    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing signature")

    secret = settings.GITHUB_WEBHOOK_SECRET.encode()
    expected_signature = "sha256=" + hmac.new(secret, request_body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

def parse_webhook_payload(content_type: Optional[str], body: bytes) -> Dict[str, Any]:
    """Parse a webhook body, rejecting anything that isn't a JSON object"""
    media_type = (content_type or "").split(";")[0].strip().lower()
    if media_type != "application/json":
        # GitHub's default webhook content type is form-encoded, so say how to fix it
        raise HTTPException(
            status_code=415,
            detail="Webhook content type must be application/json (set it in the GitHub webhook settings)"
        )

    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=422, detail="Webhook body is not valid JSON")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Webhook body must be a JSON object")
    return payload

def _as_dict(value: Any) -> Dict[str, Any]:
    """Treat a missing, null or non-object payload field as empty"""
    return value if isinstance(value, dict) else {}

def _get_pr_payload_data(payload: Dict[str, Any]) -> tuple:
    """Helper function to extract common payload data"""
    action = payload.get("action")
    pr_number = payload.get("number")
    pr_data = _as_dict(payload.get("pull_request"))
    repo_data = _as_dict(payload.get("repository"))
    return action, pr_number, pr_data, repo_data

def pr_state(pr_data: Dict[str, Any]) -> str:
    """The PR's state: open, closed or merged (GitHub reports merged PRs as closed)"""
    if pr_data.get("merged"):
        return "merged"
    return pr_data.get("state") or "open"

def extract_pr_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract PR data from GitHub webhook payload"""
    action, pr_number, pr_data, repo_data = _get_pr_payload_data(payload)
    head = _as_dict(pr_data.get("head"))
    
    # Return only the fields needed for the PR model
    return {
        "number": pr_number,
        "repo_name": repo_data.get("name"),
        "repo_full_name": repo_data.get("full_name"),
        "branch": head.get("ref"),
        "author": _as_dict(pr_data.get("user")).get("login"),
        "title": pr_data.get("title"),
        "status": pr_state(pr_data),
        "github_url": pr_data.get("html_url"),
        "diff_url": pr_data.get("diff_url"),
        "head_sha": head.get("sha"),
    }

def extract_pr_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract metadata about the PR for logging and processing"""
    action, pr_number, pr_data, repo_data = _get_pr_payload_data(payload)
    
    return {
        "action": action,
        "pr_number": pr_number,
        "pr_data": pr_data,
        "repo_data": repo_data
    }


class GitHubAPIError(Exception):
    """A GitHub API request failed; the message says what to do about it"""


def _diff_error_message(status: int, body: str, repo_full_name: str, number: int) -> str:
    pr = f"{repo_full_name}#{number}"
    if status == 401:
        return f"GitHub rejected GITHUB_TOKEN while fetching {pr}; check it's valid and hasn't expired"
    if status == 403 and "rate limit" in body.lower():
        hint = "" if settings.GITHUB_TOKEN else "; set GITHUB_TOKEN for a higher limit"
        return f"GitHub API rate limit reached while fetching {pr}{hint}"
    if status in (403, 404):
        if settings.GITHUB_TOKEN:
            return (f"GitHub returned {status} for {pr}: GITHUB_TOKEN needs read access to "
                    "this repository's pull requests and contents")
        return (f"GitHub returned {status} for {pr}: if the repository is private, set "
                "GITHUB_TOKEN to a token with read access to its pull requests and contents")
    if status == 406:
        return f"The diff for {pr} is too large for the GitHub API to return"
    return f"GitHub returned {status} while fetching the diff for {pr}"


async def fetch_pr_diff(repo_full_name: str, number: int) -> str:
    """
    Fetch a PR's diff from the GitHub REST API.
    
    Uses GITHUB_TOKEN when set, which private repositories need. (The diff_url in webhook
    payloads is a github.com page, which doesn't accept API tokens.)
    """
    url = f"{settings.GITHUB_API_URL.rstrip('/')}/repos/{repo_full_name}/pulls/{number}"
    headers = {
        "Accept": "application/vnd.github.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    
    try:
        response = await fetch_with_retry(url, "GET", headers=headers)
    except httpx.HTTPStatusError as e:
        raise GitHubAPIError(
            _diff_error_message(e.response.status_code, e.response.text, repo_full_name, number)
        ) from e
    return response.text

