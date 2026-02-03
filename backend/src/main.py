import os
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
import hmac
import hashlib
from typing import Optional
from pydantic import BaseModel
import logging
from datetime import datetime
from database import get_db, create_pr, update_pr_status, init_db

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

    # Here you would:
    # 2. Trigger AI analysis
    # 3. Return appropriate response

    return {
        "status": "success",
        "pr_number": pr_number,
        "action": action,
        "repository": repo_data.get("full_name"),
        "database_id": pr_record.id,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)