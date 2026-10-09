"""
Deciding when to analyse a PR, and running the analysis after the webhook has responded.

GitHub gives up on a webhook after 10 seconds, and an AI review can take much longer, so
the webhook only stores the PR and queues the analysis.
"""
import logging
from typing import Optional

from fastapi.concurrency import run_in_threadpool

from codemop.config import CONFIG_FILE, ConfigError, RepoConfig, parse_config
from codemop.github.client import PullRequestRef, fetch_pr_diff, fetch_repo_file
from codemop.providers import create_model
from codemop.providers.base import ReviewModel
from codemop.review.chunks import DEFAULT_IGNORED_PATHS
from codemop.review.pipeline import ReviewReport, review_diff

from app.config import settings
from app.db.pr_repository import pr_repository
from app.db.session import session_scope
from app.models.pr import PR, pr_label
from app.services.suggestion_service import suggestion_service

logger = logging.getLogger(__name__)

# PR actions that can change the code under review
ANALYZE_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


def skip_reason(action: Optional[str], is_draft: bool, pr: PR) -> Optional[str]:
    """Why this event shouldn't trigger an analysis, or None if it should"""
    if not settings.ai_key_configured:
        return f"no API key for {settings.AI_PROVIDER}: set AI_API_KEY (or {settings.ai_key_env})"
    if action not in ANALYZE_ACTIONS:
        return f"'{action}' events don't change the code"
    if is_draft:
        return "draft PR (it will be analysed when marked ready for review)"
    if pr.head_sha is not None and pr.head_sha == pr.analyzed_sha:
        return f"commit {pr.head_sha[:7]} has already been analysed"
    return None


def review_model() -> ReviewModel:
    """The model configured by AI_PROVIDER, AI_MODEL, AI_BASE_URL and AI_API_KEY"""
    return create_model(
        settings.AI_PROVIDER,
        settings.AI_MODEL or None,
        base_url=settings.AI_BASE_URL or None,
        api_key=settings.AI_API_KEY or None,
    )


async def repo_config(repo_full_name: str) -> RepoConfig:
    """
    The repository's .codemop.yml (from its default branch), or the defaults. A broken file is
    logged and ignored rather than stopping reviews.
    """
    text = await fetch_repo_file(
        repo_full_name, CONFIG_FILE, token=settings.GITHUB_TOKEN or None, api_url=settings.GITHUB_API_URL
    )
    if text is None:
        return RepoConfig()
    try:
        return parse_config(text, source=f"{repo_full_name}/{CONFIG_FILE}")
    except ConfigError as e:
        logger.warning(f"Using default review settings: {e}")
        return RepoConfig()


def store_report(pr_id: int, label: str, head_sha: Optional[str], report: ReviewReport) -> bool:
    """
    Replace the PR's suggestions with the report's, unless the PR is gone or has newer
    commits; returns whether they were stored. Synchronous database work, run in a thread.
    """
    with session_scope() as db:
        pr = pr_repository.get(db, pr_id)
        if pr is None:
            logger.warning(f"{label} no longer exists; discarding its analysis")
            return False
        if head_sha is not None and pr.head_sha != head_sha:
            logger.info(f"{label} has new commits since {head_sha[:7]} was analysed; discarding stale results")
            return False
        suggestion_service.replace_for_pr(db, pr, report.suggestions, head_sha)
        return True


async def analyze_pr_in_background(
    pr_id: int, repo_full_name: str, number: int, head_sha: Optional[str]
) -> None:
    """Review a PR's diff with codemop, and replace the PR's suggestions with the results"""
    label = pr_label(repo_full_name, number)
    try:
        diff = await fetch_pr_diff(
            PullRequestRef(repo_full_name, number),
            token=settings.GITHUB_TOKEN or None,
            api_url=settings.GITHUB_API_URL,
        )
        config = await repo_config(repo_full_name)
        report = await review_diff(
            diff, review_model(),
            chunk_tokens=config.chunk_tokens,
            min_confidence=config.min_confidence,
            ignored_paths=[*DEFAULT_IGNORED_PATHS, *config.ignore],
        )
    except Exception as e:
        # analyzed_sha stays unset, so the next push or a redelivery retries
        logger.error(f"Analysis failed for {label}: {str(e)}")
        return
    
    if not report.complete:
        # Keep the old suggestions and leave analyzed_sha unset, so it's retried
        reasons = "; ".join(sorted({failed.reason for failed in report.failed}))
        logger.error(f"Review of {label} with {report.model} was incomplete: {reasons}")
        return
    for skipped in report.skipped:
        logger.info(f"Skipped {skipped.path} in {label}: {skipped.reason}")
    
    try:
        if not await run_in_threadpool(store_report, pr_id, label, head_sha, report):
            return
        cost = f", about ${report.cost:.4f}" if report.cost else ""
        logger.info(
            f"💾 Stored {len(report.suggestions)} suggestions for {label} from {report.model} "
            f"({report.usage.input_tokens:,} input / {report.usage.output_tokens:,} output tokens{cost})"
        )
    except Exception as e:
        logger.error(f"💾 Failed to store suggestions for {label}: {str(e)}")
