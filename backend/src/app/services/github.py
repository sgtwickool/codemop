import hmac
import hashlib
from fastapi import HTTPException, Header
from typing import Optional
import logging
from pydantic import ValidationError
from app.config import settings
from app.schemas.github_webhook import PullRequestEvent

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
