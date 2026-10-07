import hmac
import json
import hashlib
from fastapi import HTTPException, Header
from typing import Optional, Dict, Any
import logging
from app.config import settings

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