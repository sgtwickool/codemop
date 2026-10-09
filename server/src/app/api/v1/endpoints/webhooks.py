from dataclasses import dataclass
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException, Header
from fastapi.concurrency import run_in_threadpool
from typing import Optional
from app.models.pr import pr_label
from app.schemas.github_webhook import PullRequestEvent
from app.services.github import validate_github_webhook_signature, parse_pull_request_event
from app.services.pr_service import pr_service
from app.services.pr_analysis import analyze_pr_in_background, skip_reason
from app.db.session import session_scope
from app.db.webhook_delivery_repository import webhook_delivery_repository
import logging
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredPR:
    id: int
    head_sha: Optional[str]
    skip_reason: Optional[str]  # why it won't be analysed, or None if it will


def store_event(event: PullRequestEvent, delivery_id: Optional[str], event_name: str) -> Optional[StoredPR]:
    """
    Store the PR and the delivery in one transaction, so if this fails a redelivery is
    processed again. None if the delivery was already processed. Synchronous database
    work: the handler runs it in a thread, so it doesn't block the event loop.
    """
    with session_scope() as db:
        if delivery_id and not webhook_delivery_repository.record(db, delivery_id, event_name):
            return None
        # Read everything needed from the PR before the commit, which expires it
        pr = pr_service.create_pr(db, event.pr_fields())
        stored = StoredPR(pr.id, pr.head_sha, skip_reason(event.action, event.pull_request.draft, pr))
        webhook_delivery_repository.prune(db)
        return stored


# Deliberately not rate limited: every delivery comes from GitHub's few IP addresses (or a
# proxy's), so a limit would only drop real events, and GitHub doesn't retry a 429. Forged
# requests fail the cheap signature check, and analysis runs at most once per commit.
@router.post("/github/webhook")
async def handle_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_delivery: Optional[str] = Header(None),
):
    """
    Store the PR from a pull_request event and queue an AI analysis if the code changed.
    
    Responds straight away; the analysis runs afterwards (GitHub gives up after 10 seconds).
    """
    # Authenticate every request before acting on it, whatever the event
    request_body = await request.body()
    await validate_github_webhook_signature(request_body, x_hub_signature_256)
    
    # GitHub sends a ping when the webhook is created; the reply shows in its delivery log
    if x_github_event == "ping":
        logger.info("Received ping from GitHub")
        return {"status": "pong", "message": "CodeMop is receiving webhooks from GitHub"}
    
    # Only process pull_request events
    if x_github_event != "pull_request":
        logger.info(f"Received non-PR event: {x_github_event}")
        return {"status": "ignored", "reason": "not a pull_request event"}
    
    event = parse_pull_request_event(request.headers.get("content-type"), request_body)
    label = pr_label(event.repository.full_name, event.number)
    
    logger.info(f"Processing {label} - Action: {event.action}")
    logger.info(f"PR Title: {event.pull_request.title}")
    logger.info(f"Author: {event.pull_request.user.login}")
    logger.info(f"Branch: {event.pull_request.head.ref}")
    
    try:
        stored = await run_in_threadpool(store_event, event, x_github_delivery, x_github_event)
    except Exception as e:
        logger.error(f"Failed to store PR data: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error while storing PR")
    
    # GitHub redelivers on timeouts and manual retries; each delivery is only processed once
    if stored is None:
        logger.info(f"Ignoring redelivery {x_github_delivery} for {label}")
        return {"status": "duplicate", "reason": f"delivery {x_github_delivery} was already processed"}
    
    if stored.skip_reason is None:
        logger.info(f"Queueing AI analysis for {label}")
        background_tasks.add_task(
            analyze_pr_in_background, stored.id, event.repository.full_name, event.number, stored.head_sha
        )
        analysis = {"analysis": "queued"}
    else:
        logger.info(f"Not analysing {label}: {stored.skip_reason}")
        analysis = {"analysis": "skipped", "reason": stored.skip_reason}
    
    return {
        "status": "success",
        "pr_number": event.number,
        "action": event.action,
        "repository": event.repository.full_name,
        "database_id": stored.id,
        **analysis,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
