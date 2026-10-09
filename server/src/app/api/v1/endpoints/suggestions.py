from fastapi import APIRouter, HTTPException, Depends, Request, Path
from sqlalchemy.orm import Session
from app.core.rate_limit import limiter
from app.core.security_config import RATE_LIMITS
from app.models.pr import PR
from app.services.pr_service import pr_service
from app.services.suggestion_service import suggestion_service
from app.db.session import get_db
from app.core.security import get_api_key
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Database IDs are 32-bit integers; larger values can't match a PR
MAX_DB_ID = 2**31 - 1
# PR numbers are stored as 64-bit integers
MAX_PR_NUMBER = 2**63 - 1
# GitHub owner and repository names: letters, digits, '-', '_' and '.'
GITHUB_NAME_PATTERN = r"^[A-Za-z0-9_.-]+$"


def _suggestions_response(db: Session, pr: PR) -> dict:
    """The suggestions for a PR, with the PR's details"""
    try:
        suggestions = suggestion_service.get_suggestions_by_pr_id(db, pr.id)
    except Exception as e:
        logger.error(f"Error fetching suggestions for PR {pr.id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving suggestions")
    
    formatted_suggestions = [
        {
            "id": suggestion.id,
            "file_path": suggestion.file_path,
            "line_number": suggestion.line_number,
            "end_line": suggestion.end_line,
            "severity": suggestion.severity,
            "title": suggestion.title,
            "description": suggestion.description,
            "fix": suggestion.fix,
            "confidence": suggestion.confidence,
            "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None
        }
        for suggestion in suggestions
    ]
    
    return {
        "pr_id": pr.id,
        "number": pr.number,
        "repo": pr.repo_full_name,
        "title": pr.title,
        "status": pr.status,
        "head_sha": pr.head_sha,
        "analyzed_sha": pr.analyzed_sha,
        "suggestions_count": len(formatted_suggestions),
        "suggestions": formatted_suggestions
    }


@router.get("/repos/{owner}/{repo}/pulls/{number}/suggestions")
@limiter.limit(RATE_LIMITS["suggestions"])
def get_suggestions_by_number(
    request: Request,
    owner: str = Path(pattern=GITHUB_NAME_PATTERN, max_length=100),
    repo: str = Path(pattern=GITHUB_NAME_PATTERN, max_length=100),
    number: int = Path(ge=1, le=MAX_PR_NUMBER),
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)
):
    """
    Get the suggestions for a PR, identified the way GitHub does (owner/repo and PR number)
    """
    try:
        pr = pr_service.get_pr_by_number(db, f"{owner}/{repo}", number)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _suggestions_response(db, pr)


@router.get("/pr/{pr_id}/suggestions")
@limiter.limit(RATE_LIMITS["suggestions"])
def get_suggestions(
    request: Request,
    pr_id: int = Path(ge=1, le=MAX_DB_ID),
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)
):
    """
    Get the suggestions for a PR by CodeMop's database ID (the webhook response's `database_id`)
    """
    try:
        pr = pr_service.get_pr_by_id(db, pr_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"PR {pr_id} not found")
    return _suggestions_response(db, pr)
