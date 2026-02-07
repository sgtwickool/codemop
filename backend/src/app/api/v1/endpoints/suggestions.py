from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Dict, Any
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.security_config import RATE_LIMITS
from app.services.pr_service import pr_service
from app.services.suggestion_service import suggestion_service
from app.db.session import get_db
from app.core.security import get_api_key
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize limiter for this router
limiter = Limiter(key_func=get_remote_address)

@router.get("/pr/{pr_id}/suggestions")
@limiter.limit(RATE_LIMITS["suggestions"])
async def get_suggestions(
    request: Request,
    pr_id: int,
    api_key: str = Depends(get_api_key)
):
    """
    Get all suggestions for a specific PR
    
    Args:
        pr_id: The database ID of the PR
        api_key: Valid API key for authentication
    
    Returns:
        List of suggestions with line numbers, descriptions, and fixes
    """
    db = next(get_db())
    try:
        # First check if PR exists
        pr = pr_service.get_pr_by_id(db, pr_id)
        
        # Get all suggestions for this PR
        suggestions = suggestion_service.get_suggestions_by_pr_id(db, pr_id)
        
        if not suggestions:
            return {
                "pr_id": pr_id,
                "github_id": pr.github_id,
                "repo": pr.repo_full_name,
                "title": pr.title,
                "suggestions": [],
                "message": "No suggestions found for this PR"
            }
        
        # Format suggestions for API response
        formatted_suggestions = []
        for suggestion in suggestions:
            formatted_suggestions.append({
                "id": suggestion.id,
                "line_number": suggestion.line_number,
                "file_path": suggestion.file_path,
                "description": suggestion.description,
                "fix": suggestion.fix,
                "confidence": suggestion.confidence,
                "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None
            })
        
        return {
            "pr_id": pr_id,
            "github_id": pr.github_id,
            "repo": pr.repo_full_name,
            "title": pr.title,
            "status": pr.status,
            "suggestions_count": len(formatted_suggestions),
            "suggestions": formatted_suggestions
        }
        
    except Exception as e:
        logger.error(f"Error fetching suggestions for PR {pr_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving suggestions: {str(e)}"
        )
    finally:
        db.close()