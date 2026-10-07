import hmac
import hashlib
from fastapi import HTTPException, Header
from typing import Optional
import logging
import httpx
from pydantic import ValidationError
from app.config import settings
from app.models.pr import pr_label
from app.schemas.github_webhook import PullRequestEvent
from app.utils import http

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

def parse_pull_request_event(content_type: Optional[str], body: bytes) -> PullRequestEvent:
    """Parse and validate a pull_request webhook body; anything malformed is a 4xx"""
    media_type = (content_type or "").split(";")[0].strip().lower()
    if media_type != "application/json":
        # GitHub's default webhook content type is form-encoded, so say how to fix it
        raise HTTPException(
            status_code=415,
            detail="Webhook content type must be application/json (set it in the GitHub webhook settings)"
        )

    try:
        return PullRequestEvent.model_validate_json(body)
    except ValidationError as e:
        errors = e.errors()
        missing = [".".join(map(str, error["loc"])) for error in errors if error["type"] == "missing"]
        if missing:
            detail = f"pull_request payload is missing required fields: {', '.join(missing)}"
        else:
            error = errors[0]
            location = ".".join(map(str, error["loc"])) or "body"
            detail = f"Invalid pull_request payload ({location}): {error['msg']}"
        raise HTTPException(status_code=422, detail=detail)


class GitHubAPIError(Exception):
    """A GitHub API request failed; the message says what to do about it"""


def _diff_error_message(status: int, body: str, repo_full_name: str, number: int) -> str:
    pr = pr_label(repo_full_name, number)
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
        response = await http.fetch_with_retry(url, "GET", headers=headers)
    except httpx.HTTPStatusError as e:
        raise GitHubAPIError(
            _diff_error_message(e.response.status_code, e.response.text, repo_full_name, number)
        ) from e
    return response.text

