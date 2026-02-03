import os
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
import hmac
import hashlib
from typing import Optional
from pydantic import BaseModel
import logging
from datetime import datetime
import httpx
import asyncio
from database import get_db, create_pr, update_pr_status, init_db, create_suggestion

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Initialize database on startup
@app.on_event("startup")
def on_startup():
    init_db()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GitHub Webhook Secret from environment
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

# AI API Configuration
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_API_URL = os.getenv("AI_API_URL", "https://api.mistral.ai/v1/analysis")
MAX_RETRIES = 3
RETRY_DELAY = 1.0

class PRData(BaseModel):
    action: str
    number: int
    pull_request: dict
    repository: dict

@app.post("/github/webhook")
async def handle_github_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None)
):
    # Validate webhook signature
    if GITHUB_WEBHOOK_SECRET:
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing signature")

        body = await request.body()
        secret = GITHUB_WEBHOOK_SECRET.encode()
        expected_signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_signature, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Only process pull_request events
    if x_github_event != "pull_request":
        logger.info(f"Received non-PR event: {x_github_event}")
        return {"status": "ignored", "reason": "not a pull_request event"}

    payload = await request.json()
    action = payload.get("action")
    pr_number = payload.get("number")
    pr_data = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})

    logger.info(f"Processing PR #{pr_number} - Action: {action}")
    logger.info(f"Repository: {repo_data.get('full_name')}")
    logger.info(f"PR Title: {pr_data.get('title')}")
    logger.info(f"Author: {pr_data.get('user', {}).get('login')}")
    logger.info(f"Branch: {pr_data.get('head', {}).get('ref')}")

    # Store PR data in database
    db = next(get_db())
    try:
        pr_record = create_pr(db, {
            "github_id": pr_number,
            "repo_name": repo_data.get("name"),
            "repo_full_name": repo_data.get("full_name"),
            "branch": pr_data.get("head", {}).get("ref"),
            "author": pr_data.get("user", {}).get("login"),
            "title": pr_data.get("title"),
            "status": action,
            "github_url": pr_data.get("html_url"),
            "diff_url": pr_data.get("diff_url")
        })
        logger.info(f"Stored PR #{pr_number} in database with ID {pr_record.id}")
    except Exception as e:
        logger.error(f"Failed to store PR data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        db.close()

    # Trigger AI analysis
    suggestions = []
    if AI_API_KEY and pr_data.get("diff_url"):
        try:
            suggestions = await analyze_pr_with_ai(pr_data.get("diff_url"))
            logger.info(f"AI analysis completed for PR #{pr_number}: {len(suggestions)} suggestions")
        except Exception as e:
            logger.error(f"AI analysis failed for PR #{pr_number}: {str(e)}")

    # Store suggestions in database
    if suggestions:
        db = next(get_db())
        try:
            for suggestion in suggestions:
                create_suggestion(db, {
                    "pr_id": pr_record.id,
                    "line_number": suggestion.get("line_number"),
                    "file_path": suggestion.get("file_path"),
                    "description": suggestion.get("description"),
                    "fix": suggestion.get("fix"),
                    "confidence": suggestion.get("confidence")
                })
            logger.info(f"Stored {len(suggestions)} suggestions for PR #{pr_number}")
        except Exception as e:
            logger.error(f"Failed to store suggestions for PR #{pr_number}: {str(e)}")
        finally:
            db.close()

    return {
        "status": "success",
        "pr_number": pr_number,
        "action": action,
        "repository": repo_data.get("full_name"),
        "database_id": pr_record.id,
        "suggestions_count": len(suggestions),
        "timestamp": datetime.utcnow().isoformat()
    }

async def fetch_diff_content(diff_url: str) -> str:
    """Fetch the actual diff content from GitHub"""
    async with httpx.AsyncClient() as client:
        response = await client.get(diff_url)
        response.raise_for_status()
        return response.text

async def analyze_pr_with_ai(diff_url: str) -> list:
    """
    Call AI API to analyze PR diff and generate suggestions
    With retry logic for resilience
    """
    diff_content = await fetch_diff_content(diff_url)
    
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    AI_API_URL,
                    json={
                        "diff": diff_content,
                        "model": "codemop-analysis",
                        "max_suggestions": 10
                    },
                    headers={
                        "Authorization": f"Bearer {AI_API_KEY}",
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                
                # Parse and validate the response
                data = response.json()
                suggestions = data.get("suggestions", [])
                
                # Validate suggestion format
                validated_suggestions = []
                for suggestion in suggestions:
                    if all(key in suggestion for key in ["line_number", "description", "fix", "confidence"]):
                        validated_suggestions.append(suggestion)
                    else:
                        logger.warning(f"Invalid suggestion format: {suggestion}")
                
                return validated_suggestions
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                # Rate limited, wait and retry
                wait_time = RETRY_DELAY * (attempt + 1)
                logger.warning(f"Rate limited, retrying in {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES})")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"AI API request failed: {str(e)}")
                raise
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (attempt + 1)
                logger.warning(f"AI API error, retrying in {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"AI analysis failed after {MAX_RETRIES} attempts: {str(e)}")
                raise
    
    return []

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)