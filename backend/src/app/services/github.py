import hmac
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
    if settings.GITHUB_WEBHOOK_SECRET:
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing signature")

        secret = settings.GITHUB_WEBHOOK_SECRET.encode()
        expected_signature = "sha256=" + hmac.new(secret, request_body, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_signature, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")

def _get_pr_payload_data(payload: Dict[str, Any]) -> tuple:
    """Helper function to extract common payload data"""
    action = payload.get("action")
    pr_number = payload.get("number")
    pr_data = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})
    return action, pr_number, pr_data, repo_data

def extract_pr_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract PR data from GitHub webhook payload"""
    action, pr_number, pr_data, repo_data = _get_pr_payload_data(payload)
    
    # Return only the fields needed for the PR model
    return {
        "github_id": pr_number,
        "repo_name": repo_data.get("name"),
        "repo_full_name": repo_data.get("full_name"),
        "branch": pr_data.get("head", {}).get("ref"),
        "author": pr_data.get("user", {}).get("login"),
        "title": pr_data.get("title"),
        "status": action,
        "github_url": pr_data.get("html_url"),
        "diff_url": pr_data.get("diff_url")
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