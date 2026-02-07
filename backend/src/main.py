import os
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Header, Depends, Security
from fastapi.security import APIKeyHeader
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

# Load environment variables from .env file
load_dotenv('/home/sgtwickool/repos/codemop/.env')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Key Security
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    """Extract and validate API key from Authorization header"""
    if not api_key_header:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing"
        )
    
    # Handle "Bearer " prefix
    if api_key_header.startswith("Bearer "):
        api_key = api_key_header[7:].strip()
    else:
        api_key = api_key_header.strip()
    
    if api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return api_key

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
AI_API_URL = os.getenv("AI_API_URL", "https://api.mistral.ai/v1/chat/completions")
AI_MODEL = os.getenv("AI_MODEL", "codestral-latest")

# API Authentication
API_KEY = os.getenv("API_KEY", "")

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
            logger.info(f"Starting AI analysis for PR #{pr_number}")
            suggestions = await analyze_pr_with_ai(pr_data.get("diff_url"))
            logger.info(f"✅ AI analysis completed for PR #{pr_number}: {len(suggestions)} suggestions")
        except httpx.TimeoutException as e:
            logger.error(f"⏰ AI API timeout for PR #{pr_number}: {str(e)}")
            logger.error("   Consider increasing timeout or checking network connectivity")
        except httpx.HTTPStatusError as e:
            logger.error(f"🔌 AI API HTTP error for PR #{pr_number}: {e.response.status_code} - {str(e)}")
            if e.response.status_code == 401:
                logger.error("   Authentication failed - check AI_API_KEY")
            elif e.response.status_code == 429:
                logger.error("   Rate limited - consider increasing retry delay")
            elif e.response.status_code >= 500:
                logger.error("   AI service unavailable - try again later")
        except Exception as e:
            logger.error(f"💥 AI analysis failed for PR #{pr_number}: {str(e)}")
            logger.error("   This might be a network issue or API configuration problem")

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
            logger.info(f"💾 Stored {len(suggestions)} suggestions for PR #{pr_number}")
        except Exception as e:
            logger.error(f"💾 Failed to store suggestions for PR #{pr_number}: {str(e)}")
            # Don't fail the entire webhook if suggestion storage fails
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
    Call Mistral AI API to analyze PR diff and generate code suggestions
    Uses chat completions API with structured prompting for code analysis
    """
    diff_content = await fetch_diff_content(diff_url)
    
    # Create a prompt for code analysis
    prompt = f"""You are an expert code reviewer. Analyze the following code diff and provide specific suggestions for improvements, bug fixes, and best practices.

Requirements:
1. Focus on real issues: bugs, security vulnerabilities, performance problems
2. Provide actionable suggestions with specific line numbers
3. Include confidence scores (0.0-1.0) for each suggestion
4. Return suggestions in JSON format only

Code Diff:
```
{diff_content[:10000]}  # Limit to first 10k characters
```

Response Format:
{{
  "suggestions": [
    {{
      "line_number": 42,
      "file_path": "filename.py",
      "description": "Description of the issue",
      "fix": "Suggested fix code",
      "confidence": 0.95
    }}
  ]
}}

Only return valid JSON, no additional text."""
    
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    AI_API_URL,
                    json={
                        "model": AI_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a helpful code review assistant that provides specific, actionable suggestions for code improvements."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.3,
                        "max_tokens": 2000
                    },
                    headers={
                        "Authorization": f"Bearer {AI_API_KEY}",
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                
                # Parse the response
                data = response.json()
                
                # Extract the AI's response content
                if 'choices' in data and len(data['choices']) > 0:
                    content = data['choices'][0]['message']['content']
                    
                    # Try to parse the JSON response
                    try:
                        suggestions_data = json.loads(content)
                        suggestions = suggestions_data.get("suggestions", [])
                        
                        # Validate and normalize suggestions
                        validated_suggestions = []
                        for suggestion in suggestions:
                            validated_suggestion = {
                                "line_number": suggestion.get("line_number", 1),
                                "file_path": suggestion.get("file_path", "unknown.py"),
                                "description": suggestion.get("description", "No description"),
                                "fix": suggestion.get("fix", "No fix provided"),
                                "confidence": float(suggestion.get("confidence", 0.5))
                            }
                            validated_suggestions.append(validated_suggestion)
                        
                        return validated_suggestions
                        
                    except json.JSONDecodeError:
                        logger.warning(f"AI response is not valid JSON: {content[:200]}")
                        # Try to extract suggestions from plain text
                        return extract_suggestions_from_text(content)
                else:
                    logger.warning(f"Unexpected AI API response format: {data}")
                    return []
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                # Rate limited, wait and retry
                wait_time = RETRY_DELAY * (attempt + 1)
                logger.warning(f"Rate limited, retrying in {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES})")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"AI API request failed: {str(e)}")
                if e.response.status_code == 401:
                    logger.error("Authentication failed - check AI_API_KEY")
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

def extract_suggestions_from_text(text: str) -> list:
    """Fallback method to extract suggestions from plain text response"""
    suggestions = []
    lines = text.split('\n')
    
    current_suggestion = {}
    in_suggestion = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if "line" in line.lower() and "number" in line.lower():
            if current_suggestion:
                suggestions.append(current_suggestion)
            current_suggestion = {"confidence": 0.7}
            in_suggestion = True
            
            # Extract line number
            try:
                line_num = int(''.join(filter(str.isdigit, line)))
                current_suggestion["line_number"] = line_num
            except:
                current_suggestion["line_number"] = 1
        elif in_suggestion and ":" in line and not current_suggestion.get("description"):
            current_suggestion["description"] = line.split(":", 1)[1].strip()
        elif in_suggestion and (line.startswith("Fix:") or line.startswith("fix:")):
            current_suggestion["fix"] = line.split(":", 1)[1].strip()
        elif in_suggestion and line.startswith("File:"):
            current_suggestion["file_path"] = line.split(":", 1)[1].strip()
    
    if current_suggestion:
        suggestions.append(current_suggestion)
    
    return suggestions

@app.get("/pr/{pr_id}/suggestions")
async def get_suggestions(
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
        # Import PR model here to avoid circular imports
        from database import PR, Suggestion
        
        # First check if PR exists
        pr = db.query(PR).filter(PR.id == pr_id).first()
        if not pr:
            raise HTTPException(
                status_code=404,
                detail=f"PR with ID {pr_id} not found"
            )
        
        # Get all suggestions for this PR
        suggestions = db.query(Suggestion).filter(Suggestion.pr_id == pr_id).all()
        
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

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)