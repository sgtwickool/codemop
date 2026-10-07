from fastapi import APIRouter, Request, HTTPException, Header, Depends
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
from app.services.suggestion_service import suggestion_service
from app.services.ai_analysis import analyze_pr_with_ai
from app.db.session import get_db
import logging
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/github/webhook")
@limiter.limit(RATE_LIMITS["webhook"])
async def handle_github_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
    db: Session = Depends(get_db)  # Proper dependency injection
):
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
    missing_fields = [field for field, value in pr_db_data.items() if value is None]
    if missing_fields:
        raise HTTPException(
            status_code=422,
            detail=f"pull_request payload is missing required fields: {', '.join(missing_fields)}"
        )
    
    # Extract PR metadata for logging
    pr_metadata = extract_pr_metadata(payload)
    
    logger.info(f"Processing PR #{pr_metadata['pr_number']} - Action: {pr_metadata['action']}")
    logger.info(f"Repository: {pr_db_data['repo_full_name']}")
    logger.info(f"PR Title: {pr_db_data['title']}")
    logger.info(f"Author: {pr_db_data['author']}")
    logger.info(f"Branch: {pr_db_data['branch']}")
    
    # Store PR data in database
    try:
        pr_record = pr_service.create_pr(db, pr_db_data)
    except Exception as e:
        logger.error(f"Failed to store PR data: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error while storing PR")
    
    # Trigger AI analysis
    suggestions = []
    diff_url = pr_db_data.get("diff_url")
    if isinstance(diff_url, str) and diff_url:
        try:
            logger.info(f"Starting AI analysis for PR #{pr_metadata['pr_number']}")
            suggestions = await analyze_pr_with_ai(diff_url)
        except Exception as e:
            logger.error(f"AI analysis failed for PR #{pr_metadata['pr_number']}: {str(e)}")
            # Don't fail the entire webhook if AI analysis fails
    
    # Store suggestions in database
    if suggestions:
        try:
            suggestion_service.create_suggestions_batch(db, pr_record.id, suggestions)
            logger.info(f"💾 Stored {len(suggestions)} suggestions for PR #{pr_metadata['pr_number']}")
        except Exception as e:
            logger.error(f"💾 Failed to store suggestions for PR #{pr_metadata['pr_number']}: {str(e)}")
            # Don't fail the entire webhook if suggestion storage fails
    
    return {
        "status": "success",
        "pr_number": pr_metadata['pr_number'],
        "action": pr_metadata['action'],
        "repository": pr_db_data['repo_full_name'],
        "database_id": pr_record.id,
        "suggestions_count": len(suggestions),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }