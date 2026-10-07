"""
Deciding when to analyse a PR, and running the analysis after the webhook has responded.

GitHub gives up on a webhook after 10 seconds, and an AI review can take much longer, so
the webhook only stores the PR and queues the analysis.
"""
import logging
from typing import Optional

from app.config import settings
from app.db.pr_repository import pr_repository
from app.db.session import session_scope
from app.models.pr import PR, pr_label
from app.services.ai_analysis import analyze_diff
from app.services.github import fetch_pr_diff
from app.services.suggestion_service import suggestion_service

logger = logging.getLogger(__name__)

# PR actions that can change the code under review
ANALYZE_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


def skip_reason(action: Optional[str], is_draft: bool, pr: PR) -> Optional[str]:
    """Why this event shouldn't trigger an analysis, or None if it should"""
    if not settings.AI_API_KEY:
        return "AI_API_KEY is not configured"
    if action not in ANALYZE_ACTIONS:
        return f"'{action}' events don't change the code"
    if is_draft:
        return "draft PR (it will be analysed when marked ready for review)"
    if pr.head_sha is not None and pr.head_sha == pr.analyzed_sha:
        return f"commit {pr.head_sha[:7]} has already been analysed"
    return None


async def analyze_pr_in_background(
    pr_id: int, repo_full_name: str, number: int, head_sha: Optional[str]
) -> None:
    """Fetch a PR's diff, analyse it, and replace the PR's suggestions with the results"""
    label = pr_label(repo_full_name, number)
    try:
        diff = await fetch_pr_diff(repo_full_name, number)
        suggestions = await analyze_diff(diff)
    except Exception as e:
        # analyzed_sha stays unset, so the next push or a redelivery retries
        logger.error(f"Analysis failed for {label}: {str(e)}")
        return
    
    try:
        with session_scope() as db:
            pr = pr_repository.get(db, pr_id)
            if pr is None:
                logger.warning(f"{label} no longer exists; discarding its analysis")
                return
            if head_sha is not None and pr.head_sha != head_sha:
                logger.info(f"{label} has new commits since {head_sha[:7]} was analysed; discarding stale results")
                return
            suggestion_service.replace_for_pr(db, pr, suggestions, head_sha)
        logger.info(f"💾 Stored {len(suggestions)} suggestions for {label}")
    except Exception as e:
        logger.error(f"💾 Failed to store suggestions for {label}: {str(e)}")
