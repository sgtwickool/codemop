from fastapi import APIRouter, HTTPException, Depends, Request, Path
from sqlalchemy.orm import Session
from app.core.rate_limit import limiter
from app.core.security_config import RATE_LIMITS
from app.services.pr_service import pr_service
from app.services.suggestion_service import suggestion_service
from app.db.session import get_db
from app.core.security import get_api_key
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Database IDs are 32-bit integers; larger values can't match a PR
MAX_DB_ID = 2**31 - 1

@router.get("/pr/{pr_id}/suggestions")
@limiter.limit(RATE_LIMITS["suggestions"])
async def get_suggestions(
    request: Request,
    pr_id: int = Path(ge=1, le=MAX_DB_ID),
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)  # Proper dependency injection
):
    """
    Get all suggestions for a specific PR
    
    Args:
        pr_id: The database ID of the PR
        api_key: Valid API key for authentication
        db: Database session (injected by FastAPI)
    
    Returns:
        List of suggestions with line numbers, descriptions, and fixes
    """
    try:
        pr = pr_service.get_pr_by_id(db, pr_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"PR {pr_id} not found")
    
    try:
        suggestions = suggestion_service.get_suggestions_by_pr_id(db, pr_id)
    except Exception as e:
        logger.error(f"Error fetching suggestions for PR {pr_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving suggestions")
    
    formatted_suggestions = [
        {
            "id": suggestion.id,
            "line_number": suggestion.line_number,
            "file_path": suggestion.file_path,
            "description": suggestion.description,
            "fix": suggestion.fix,
            "confidence": suggestion.confidence,
            "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None
        }
        for suggestion in suggestions
    ]
    
    return {
        "pr_id": pr_id,
        "github_id": pr.github_id,
        "repo": pr.repo_full_name,
        "title": pr.title,
        "status": pr.status,
        "suggestions_count": len(formatted_suggestions),
        "suggestions": formatted_suggestions
    }
