from fastapi import APIRouter, BackgroundTasks, Request, HTTPException, Header, Depends
from typing import Optional
from sqlalchemy.orm import Session
from app.core.rate_limit import limiter
from app.core.security_config import RATE_LIMITS
from app.services.github import (
    validate_github_webhook_signature,
    parse_webhook_payload,
    extract_pr_data,
    extract_pr_metadata,
)
from app.services.pr_service import pr_service
from app.services.pr_analysis import analyze_pr_in_background, skip_reason
from app.db.session import get_db
from app.db.webhook_delivery_repository import webhook_delivery_repository
import logging
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

# PR fields that may legitimately be missing from a payload
OPTIONAL_PR_FIELDS = {"head_sha"}

@router.post("/github/webhook")
@limiter.limit(RATE_LIMITS["webhook"])
async def handle_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_delivery: Optional[str] = Header(None),
    db: Session = Depends(get_db)  # Proper dependency injection
):
    """
    Store the PR from a pull_request event and queue an AI analysis if the code changed.
    
    Responds straight away; the analysis runs afterwards (GitHub gives up after 10 seconds).
    """
    # Only process pull_request events
    if x_github_event != "pull_request":
        logger.info(f"Received non-PR event: {x_github_event}")
        return {"status": "ignored", "reason": "not a pull_request event"}
    
    # Authenticate the request before looking at its contents
    request_body = await request.body()
    await validate_github_webhook_signature(request_body, x_hub_signature_256)
    
    payload = parse_webhook_payload(request.headers.get("content-type"), request_body)
    
    # Extract PR data for database
    pr_db_data = extract_pr_data(payload)
    missing_fields = [
        field for field, value in pr_db_data.items()
        if value is None and field not in OPTIONAL_PR_FIELDS
    ]
    if missing_fields:
        raise HTTPException(
            status_code=422,
            detail=f"pull_request payload is missing required fields: {', '.join(missing_fields)}"
        )
    
    # Extract PR metadata for logging
    pr_metadata = extract_pr_metadata(payload)
    pr_label = f"{pr_db_data['repo_full_name']}#{pr_metadata['pr_number']}"
    
    # GitHub redelivers on timeouts and manual retries; only process each delivery once
    if x_github_delivery and not webhook_delivery_repository.record(db, x_github_delivery, x_github_event):
        logger.info(f"Ignoring redelivery {x_github_delivery} for {pr_label}")
        return {"status": "duplicate", "reason": f"delivery {x_github_delivery} was already processed"}
    
    logger.info(f"Processing {pr_label} - Action: {pr_metadata['action']}")
    logger.info(f"PR Title: {pr_db_data['title']}")
    logger.info(f"Author: {pr_db_data['author']}")
    logger.info(f"Branch: {pr_db_data['branch']}")
    
    # Store the PR and the delivery together: if this fails, a redelivery is processed again
    try:
        pr_record = pr_service.create_pr(db, pr_db_data)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to store PR data: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error while storing PR")
    
    reason = skip_reason(pr_metadata["action"], bool(pr_metadata["pr_data"].get("draft")), pr_record)
    if reason is None:
        logger.info(f"Queueing AI analysis for {pr_label}")
        background_tasks.add_task(
            analyze_pr_in_background, pr_record.id, pr_record.head_sha, pr_record.diff_url
        )
        analysis = {"analysis": "queued"}
    else:
        logger.info(f"Not analysing {pr_label}: {reason}")
        analysis = {"analysis": "skipped", "reason": reason}
    
    return {
        "status": "success",
        "pr_number": pr_metadata['pr_number'],
        "action": pr_metadata['action'],
        "repository": pr_db_data['repo_full_name'],
        "database_id": pr_record.id,
        **analysis,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
