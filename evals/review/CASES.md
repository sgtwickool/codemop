# Review eval cases

Generated from `cases.yml` and `cases/` by `render_cases.py`. Line numbers are new-file lines.

| # | id | kind | expected issues |
|---|----|------|-----------------|
| 1 | [real-pr-model](#real-pr-model) | real-bug | 1 major, 0 minor |
| 2 | [real-webhook-endpoint](#real-webhook-endpoint) | real-bug | 1 major, 0 minor |
| 3 | [real-pr-storage](#real-pr-storage) | real-bug | 1 major, 2 minor |
| 4 | [real-ai-analysis](#real-ai-analysis) | real-bug | 2 major, 1 minor |
| 5 | [real-suggestions-endpoint](#real-suggestions-endpoint) | real-bug | 2 major, 0 minor |
| 6 | [real-refactor-webhooks](#real-refactor-webhooks) | real-bug | 1 major, 1 minor |
| 7 | [real-security-config](#real-security-config) | real-bug | 1 major, 2 minor |
| 8 | [real-prod-dockerfile](#real-prod-dockerfile) | real-bug | 1 major, 1 minor |
| 9 | [real-monitoring](#real-monitoring) | real-bug | 1 major, 1 minor |
| 10 | [seeded-pagination](#seeded-pagination) | seeded-bug | 1 major, 0 minor |
| 11 | [seeded-sql-injection](#seeded-sql-injection) | seeded-bug | 1 major, 0 minor |
| 12 | [seeded-missing-await](#seeded-missing-await) | seeded-bug | 1 major, 0 minor |
| 13 | [seeded-mutable-default](#seeded-mutable-default) | seeded-bug | 1 major, 0 minor |
| 14 | [seeded-async-foreach](#seeded-async-foreach) | seeded-bug | 1 major, 0 minor |
| 15 | [seeded-go-defer-before-err](#seeded-go-defer-before-err) | seeded-bug | 1 major, 0 minor |
| 16 | [seeded-inverted-expiry](#seeded-inverted-expiry) | seeded-bug | 1 major, 0 minor |
| 17 | [seeded-assignment-in-condition](#seeded-assignment-in-condition) | seeded-bug | 1 major, 0 minor |
| 18 | [seeded-regex-prefix-validation](#seeded-regex-prefix-validation) | seeded-bug | 1 major, 0 minor |
| 19 | [cross-file-arg-order](#cross-file-arg-order) | seeded-bug | 1 major, 0 minor |
| 20 | [cross-file-none-instead-of-raise](#cross-file-none-instead-of-raise) | seeded-bug | 1 major, 0 minor |
| 21 | [cross-file-units](#cross-file-units) | seeded-bug | 1 major, 0 minor |
| 22 | [cross-file-sync-to-async](#cross-file-sync-to-async) | seeded-bug | 1 major, 0 minor |
| 23 | [cross-file-renamed-key](#cross-file-renamed-key) | seeded-bug | 1 major, 0 minor |
| 24 | [clean-rename-refactor](#clean-rename-refactor) | clean | none (clean) |
| 25 | [clean-add-tests](#clean-add-tests) | clean | none (clean) |
| 26 | [clean-docs](#clean-docs) | clean | none (clean) |
| 27 | [clean-small-feature](#clean-small-feature) | clean | none (clean) |
| 28 | [clean-real-placement](#clean-real-placement) | clean | none (clean) |
| 29 | [clean-real-pricing](#clean-real-pricing) | clean | none (clean) |
| 30 | [clean-real-github-client](#clean-real-github-client) | clean | none (clean) |
| 31 | [clean-cross-file-optional-argument](#clean-cross-file-optional-argument) | clean | none (clean) |
| 32 | [clean-cross-file-generator](#clean-cross-file-generator) | clean | none (clean) |

## real-pr-model

**1. real-bug, complex, python** · commit 237b670, backend/src/database.py (fixed in ca1830a)

- **major**: github_id (the PR number) is unique across the whole table, but PR numbers restart at 1 in every repository, so PRs from different repos collide and overwrite each other (`backend/src/database.py` lines 18-18)

```diff
diff --git a/backend/src/database.py b/backend/src/database.py
new file mode 100644
index 0000000..888be8d
--- /dev/null
+++ b/backend/src/database.py
@@ -0,0 +1,52 @@
+from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Float
+from sqlalchemy.ext.declarative import declarative_base
+from sqlalchemy.orm import sessionmaker
+from datetime import datetime
+import os
+
+DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/codemop")
+
+engine = create_engine(DATABASE_URL)
+SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
+
+Base = declarative_base()
+
+class PR(Base):
+    __tablename__ = "prs"
+
+    id = Column(Integer, primary_key=True, index=True)
+    github_id = Column(Integer, unique=True, index=True)
+    repo_name = Column(String(255), index=True)
+    repo_full_name = Column(String(255))
+    branch = Column(String(255))
+    author = Column(String(255))
+    title = Column(String(512))
+    status = Column(String(50))  # open, closed, merged
+    created_at = Column(DateTime, default=datetime.utcnow)
+    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
+    github_url = Column(String(512))
+    diff_url = Column(String(512))
+
+class Suggestion(Base):
+    __tablename__ = "suggestions"
+
+    id = Column(Integer, primary_key=True, index=True)
+    pr_id = Column(Integer, ForeignKey("prs.id"))
+    line_number = Column(Integer)
+    file_path = Column(String(512))
+    description = Column(Text)
+    fix = Column(Text)
+    confidence = Column(Float)
+    created_at = Column(DateTime, default=datetime.utcnow)
+
+# Create tables
+def init_db():
+    Base.metadata.create_all(bind=engine)
+
+# Dependency
+def get_db():
+    db = SessionLocal()
+    try:
+        yield db
+    finally:
+        db.close()
\ No newline at end of file
```

## real-webhook-endpoint

**2. real-bug, simple, python, security** · commit 237b670, backend/src/main.py (fixed in 3f98f76)

- **major**: Webhook signature verification is skipped entirely when GITHUB_WEBHOOK_SECRET isn't set (fails open), so anyone can send forged events to a misconfigured server (`backend/src/main.py` lines 27-27; `backend/src/main.py` lines 42-42)

```diff
diff --git a/backend/src/main.py b/backend/src/main.py
new file mode 100644
index 0000000..aae8b8f
--- /dev/null
+++ b/backend/src/main.py
@@ -0,0 +1,89 @@
+import os
+from fastapi import FastAPI, Request, HTTPException, Header
+from fastapi.middleware.cors import CORSMiddleware
+import hmac
+import hashlib
+from typing import Optional
+from pydantic import BaseModel
+import logging
+from datetime import datetime
+
+# Configure logging
+logging.basicConfig(level=logging.INFO)
+logger = logging.getLogger(__name__)
+
+app = FastAPI()
+
+# CORS configuration
+app.add_middleware(
+    CORSMiddleware,
+    allow_origins=["*"],
+    allow_credentials=True,
+    allow_methods=["*"],
+    allow_headers=["*"],
+)
+
+# GitHub Webhook Secret from environment
+GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
+
+class PRData(BaseModel):
+    action: str
+    number: int
+    pull_request: dict
+    repository: dict
+
+@app.post("/github/webhook")
+async def handle_github_webhook(
+    request: Request,
+    x_github_event: Optional[str] = Header(None),
+    x_hub_signature_256: Optional[str] = Header(None)
+):
+    # Validate webhook signature
+    if GITHUB_WEBHOOK_SECRET:
+        if not x_hub_signature_256:
+            raise HTTPException(status_code=401, detail="Missing signature")
+
+        body = await request.body()
+        secret = GITHUB_WEBHOOK_SECRET.encode()
+        expected_signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
+
+        if not hmac.compare_digest(expected_signature, x_hub_signature_256):
+            raise HTTPException(status_code=401, detail="Invalid signature")
+
+    # Only process pull_request events
+    if x_github_event != "pull_request":
+        logger.info(f"Received non-PR event: {x_github_event}")
+        return {"status": "ignored", "reason": "not a pull_request event"}
+
+    payload = await request.json()
+    action = payload.get("action")
+    pr_number = payload.get("number")
+    pr_data = payload.get("pull_request", {})
+    repo_data = payload.get("repository", {})
+
+    logger.info(f"Processing PR #{pr_number} - Action: {action}")
+    logger.info(f"Repository: {repo_data.get('full_name')}")
+    logger.info(f"PR Title: {pr_data.get('title')}")
+    logger.info(f"Author: {pr_data.get('user', {}).get('login')}")
+    logger.info(f"Branch: {pr_data.get('head', {}).get('ref')}")
+
+    # Here you would:
+    # 1. Store PR data in database
+    # 2. Trigger AI analysis
+    # 3. Return appropriate response
+
+    return {
+        "status": "success",
+        "pr_number": pr_number,
+        "action": action,
+        "repository": repo_data.get("full_name"),
+        "timestamp": datetime.utcnow().isoformat()
+    }
+
+@app.get("/health")
+async def health_check():
+    return {"status": "healthy"}
+
+if __name__ == "__main__":
+    import uvicorn
+    uvicorn.run(app, host="0.0.0.0", port=8000)
\ No newline at end of file
```

## real-pr-storage

**3. real-bug, complex, python** · commit 6208175, backend/src/main.py and database.py (fixed in ca1830a and 24298d8)

- **major**: PRs are looked up by PR number alone, with no repository, so a PR with the same number in another repo is found and updated instead (`backend/src/database.py` lines 73-81; `backend/src/main.py` lines 80-80)
- **minor**: The PR's status is set to the webhook action (e.g. "synchronize", "labeled") rather than its state (open, closed, merged) (`backend/src/main.py` lines 86-86; `backend/src/database.py` lines 64-64)
- **minor**: The raw database exception text is returned to the client in the 500 response (`backend/src/main.py` lines 93-93)

```diff
diff --git a/backend/src/database.py b/backend/src/database.py
index 888be8d..18d3044 100644
--- a/backend/src/database.py
+++ b/backend/src/database.py
@@ -4,7 +4,7 @@ from sqlalchemy.orm import sessionmaker
 from datetime import datetime
 import os
 
-DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/codemop")
+DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://codemop:codemop@localhost:5432/codemop")
 
 engine = create_engine(DATABASE_URL)
 SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
@@ -49,4 +49,36 @@ def get_db():
     try:
         yield db
     finally:
-        db.close()
\ No newline at end of file
+        db.close()
+
+# PR storage functions
+def create_pr(db, pr_data: dict):
+    """Create a new PR record in the database"""
+    db_pr = PR(
+        github_id=pr_data.get("github_id"),
+        repo_name=pr_data.get("repo_name"),
+        repo_full_name=pr_data.get("repo_full_name"),
+        branch=pr_data.get("branch"),
+        author=pr_data.get("author"),
+        title=pr_data.get("title"),
+        status=pr_data.get("status"),
+        github_url=pr_data.get("github_url"),
+        diff_url=pr_data.get("diff_url")
+    )
+    db.add(db_pr)
+    db.commit()
+    db.refresh(db_pr)
+    return db_pr
+
+def get_pr_by_github_id(db, github_id: int):
+    """Get PR by GitHub ID"""
+    return db.query(PR).filter(PR.github_id == github_id).first()
+
+def update_pr_status(db, github_id: int, status: str):
+    """Update PR status"""
+    db_pr = get_pr_by_github_id(db, github_id)
+    if db_pr:
+        db_pr.status = status
+        db.commit()
+        db.refresh(db_pr)
+    return db_pr
\ No newline at end of file
diff --git a/backend/src/main.py b/backend/src/main.py
index aae8b8f..d8f4981 100644
--- a/backend/src/main.py
+++ b/backend/src/main.py
@@ -1,5 +1,5 @@
 import os
-from fastapi import FastAPI, Request, HTTPException, Header
+from fastapi import FastAPI, Request, HTTPException, Header, Depends
 from fastapi.middleware.cors import CORSMiddleware
 import hmac
 import hashlib
@@ -7,6 +7,7 @@ from typing import Optional
 from pydantic import BaseModel
 import logging
 from datetime import datetime
+from database import get_db, create_pr, update_pr_status, init_db
 
 # Configure logging
 logging.basicConfig(level=logging.INFO)
@@ -14,6 +15,11 @@ logger = logging.getLogger(__name__)
 
 app = FastAPI()
 
+# Initialize database on startup
+@app.on_event("startup")
+def on_startup():
+    init_db()
+
 # CORS configuration
 app.add_middleware(
     CORSMiddleware,
@@ -67,8 +73,28 @@ async def handle_github_webhook(
     logger.info(f"Author: {pr_data.get('user', {}).get('login')}")
     logger.info(f"Branch: {pr_data.get('head', {}).get('ref')}")
 
+    # Store PR data in database
+    db = next(get_db())
+    try:
+        pr_record = create_pr(db, {
+            "github_id": pr_number,
+            "repo_name": repo_data.get("name"),
+            "repo_full_name": repo_data.get("full_name"),
+            "branch": pr_data.get("head", {}).get("ref"),
+            "author": pr_data.get("user", {}).get("login"),
+            "title": pr_data.get("title"),
+            "status": action,
+            "github_url": pr_data.get("html_url"),
+            "diff_url": pr_data.get("diff_url")
+        })
+        logger.info(f"Stored PR #{pr_number} in database with ID {pr_record.id}")
+    except Exception as e:
+        logger.error(f"Failed to store PR data: {str(e)}")
+        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
+    finally:
+        db.close()
+
     # Here you would:
-    # 1. Store PR data in database
     # 2. Trigger AI analysis
     # 3. Return appropriate response
 
@@ -77,6 +103,7 @@ async def handle_github_webhook(
         "pr_number": pr_number,
         "action": action,
         "repository": repo_data.get("full_name"),
+        "database_id": pr_record.id,
         "timestamp": datetime.utcnow().isoformat()
     }
 
```

## real-ai-analysis

**4. real-bug, complex, python** · commit 87a9f94, backend/src/main.py (fixed in 495398d and 576d45f)

- **major**: The diff is silently cut at 10,000 characters before review, so most of a large PR is never reviewed and nobody is told (`backend/src/main.py` lines 184-184)
- **major**: "# Limit to first 10k characters" is inside the f-string, so it's sent to the model as part of the prompt rather than being a code comment (`backend/src/main.py` lines 184-184)
- **minor**: A 120-second timeout (with retries) on an AI call made inside the webhook request: GitHub gives up on a webhook after 10 seconds (`backend/src/main.py` lines 202-205)

````diff
diff --git a/backend/src/main.py b/backend/src/main.py
index 0e20cce..8b29e1c 100644
--- a/backend/src/main.py
+++ b/backend/src/main.py
@@ -1,4 +1,5 @@
 import os
+import json
 from fastapi import FastAPI, Request, HTTPException, Header, Depends
 from fastapi.middleware.cors import CORSMiddleware
 import hmac
@@ -36,7 +37,8 @@ GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
 
 # AI API Configuration
 AI_API_KEY = os.getenv("AI_API_KEY", "")
-AI_API_URL = os.getenv("AI_API_URL", "https://api.mistral.ai/v1/analysis")
+AI_API_URL = os.getenv("AI_API_URL", "https://api.mistral.ai/v1/chat/completions")
+AI_MODEL = os.getenv("AI_MODEL", "codestral-latest")
 MAX_RETRIES = 3
 RETRY_DELAY = 1.0
 
@@ -106,10 +108,23 @@ async def handle_github_webhook(
     suggestions = []
     if AI_API_KEY and pr_data.get("diff_url"):
         try:
+            logger.info(f"Starting AI analysis for PR #{pr_number}")
             suggestions = await analyze_pr_with_ai(pr_data.get("diff_url"))
-            logger.info(f"AI analysis completed for PR #{pr_number}: {len(suggestions)} suggestions")
+            logger.info(f"✅ AI analysis completed for PR #{pr_number}: {len(suggestions)} suggestions")
+        except httpx.TimeoutException as e:
+            logger.error(f"⏰ AI API timeout for PR #{pr_number}: {str(e)}")
+            logger.error("   Consider increasing timeout or checking network connectivity")
+        except httpx.HTTPStatusError as e:
+            logger.error(f"🔌 AI API HTTP error for PR #{pr_number}: {e.response.status_code} - {str(e)}")
+            if e.response.status_code == 401:
+                logger.error("   Authentication failed - check AI_API_KEY")
+            elif e.response.status_code == 429:
+                logger.error("   Rate limited - consider increasing retry delay")
+            elif e.response.status_code >= 500:
+                logger.error("   AI service unavailable - try again later")
         except Exception as e:
-            logger.error(f"AI analysis failed for PR #{pr_number}: {str(e)}")
+            logger.error(f"💥 AI analysis failed for PR #{pr_number}: {str(e)}")
+            logger.error("   This might be a network issue or API configuration problem")
 
     # Store suggestions in database
     if suggestions:
@@ -124,9 +139,10 @@ async def handle_github_webhook(
                     "fix": suggestion.get("fix"),
                     "confidence": suggestion.get("confidence")
                 })
-            logger.info(f"Stored {len(suggestions)} suggestions for PR #{pr_number}")
+            logger.info(f"💾 Stored {len(suggestions)} suggestions for PR #{pr_number}")
         except Exception as e:
-            logger.error(f"Failed to store suggestions for PR #{pr_number}: {str(e)}")
+            logger.error(f"💾 Failed to store suggestions for PR #{pr_number}: {str(e)}")
+            # Don't fail the entire webhook if suggestion storage fails
         finally:
             db.close()
 
@@ -149,20 +165,59 @@ async def fetch_diff_content(diff_url: str) -> str:
 
 async def analyze_pr_with_ai(diff_url: str) -> list:
     """
-    Call AI API to analyze PR diff and generate suggestions
-    With retry logic for resilience
+    Call Mistral AI API to analyze PR diff and generate code suggestions
+    Uses chat completions API with structured prompting for code analysis
     """
     diff_content = await fetch_diff_content(diff_url)
     
+    # Create a prompt for code analysis
+    prompt = f"""You are an expert code reviewer. Analyze the following code diff and provide specific suggestions for improvements, bug fixes, and best practices.
+
+Requirements:
+1. Focus on real issues: bugs, security vulnerabilities, performance problems
+2. Provide actionable suggestions with specific line numbers
+3. Include confidence scores (0.0-1.0) for each suggestion
+4. Return suggestions in JSON format only
+
+Code Diff:
+```
+{diff_content[:10000]}  # Limit to first 10k characters
+```
+
+Response Format:
+{{
+  "suggestions": [
+    {{
+      "line_number": 42,
+      "file_path": "filename.py",
+      "description": "Description of the issue",
+      "fix": "Suggested fix code",
+      "confidence": 0.95
+    }}
+  ]
+}}
+
+Only return valid JSON, no additional text."""
+    
     for attempt in range(MAX_RETRIES):
         try:
-            async with httpx.AsyncClient(timeout=30.0) as client:
+            async with httpx.AsyncClient(timeout=120.0) as client:
                 response = await client.post(
                     AI_API_URL,
                     json={
-                        "diff": diff_content,
-                        "model": "codemop-analysis",
-                        "max_suggestions": 10
+                        "model": AI_MODEL,
+                        "messages": [
+                            {
+                                "role": "system",
+                                "content": "You are a helpful code review assistant that provides specific, actionable suggestions for code improvements."
+                            },
+                            {
+                                "role": "user",
+                                "content": prompt
+                            }
+                        ],
+                        "temperature": 0.3,
+                        "max_tokens": 2000
                     },
                     headers={
                         "Authorization": f"Bearer {AI_API_KEY}",
@@ -171,19 +226,39 @@ async def analyze_pr_with_ai(diff_url: str) -> list:
                 )
                 response.raise_for_status()
                 
-                # Parse and validate the response
+                # Parse the response
                 data = response.json()
-                suggestions = data.get("suggestions", [])
-                
-                # Validate suggestion format
-                validated_suggestions = []
-                for suggestion in suggestions:
-                    if all(key in suggestion for key in ["line_number", "description", "fix", "confidence"]):
-                        validated_suggestions.append(suggestion)
-                    else:
-                        logger.warning(f"Invalid suggestion format: {suggestion}")
                 
-                return validated_suggestions
+                # Extract the AI's response content
+                if 'choices' in data and len(data['choices']) > 0:
+                    content = data['choices'][0]['message']['content']
+                    
+                    # Try to parse the JSON response
+                    try:
+                        suggestions_data = json.loads(content)
+                        suggestions = suggestions_data.get("suggestions", [])
+                        
+                        # Validate and normalize suggestions
+                        validated_suggestions = []
+                        for suggestion in suggestions:
+                            validated_suggestion = {
+                                "line_number": suggestion.get("line_number", 1),
+                                "file_path": suggestion.get("file_path", "unknown.py"),
+                                "description": suggestion.get("description", "No description"),
+                                "fix": suggestion.get("fix", "No fix provided"),
+                                "confidence": float(suggestion.get("confidence", 0.5))
+                            }
+                            validated_suggestions.append(validated_suggestion)
+                        
+                        return validated_suggestions
+                        
+                    except json.JSONDecodeError:
+                        logger.warning(f"AI response is not valid JSON: {content[:200]}")
+                        # Try to extract suggestions from plain text
+                        return extract_suggestions_from_text(content)
+                else:
+                    logger.warning(f"Unexpected AI API response format: {data}")
+                    return []
                 
         except httpx.HTTPStatusError as e:
             if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
@@ -193,6 +268,8 @@ async def analyze_pr_with_ai(diff_url: str) -> list:
                 await asyncio.sleep(wait_time)
             else:
                 logger.error(f"AI API request failed: {str(e)}")
+                if e.response.status_code == 401:
+                    logger.error("Authentication failed - check AI_API_KEY")
                 raise
         except Exception as e:
             if attempt < MAX_RETRIES - 1:
@@ -205,6 +282,43 @@ async def analyze_pr_with_ai(diff_url: str) -> list:
     
     return []
 
+def extract_suggestions_from_text(text: str) -> list:
+    """Fallback method to extract suggestions from plain text response"""
+    suggestions = []
+    lines = text.split('\n')
+    
+    current_suggestion = {}
+    in_suggestion = False
+    
+    for line in lines:
+        line = line.strip()
+        if not line:
+            continue
+            
+        if "line" in line.lower() and "number" in line.lower():
+            if current_suggestion:
+                suggestions.append(current_suggestion)
+            current_suggestion = {"confidence": 0.7}
+            in_suggestion = True
+            
+            # Extract line number
+            try:
+                line_num = int(''.join(filter(str.isdigit, line)))
+                current_suggestion["line_number"] = line_num
+            except:
+                current_suggestion["line_number"] = 1
+        elif in_suggestion and ":" in line and not current_suggestion.get("description"):
+            current_suggestion["description"] = line.split(":", 1)[1].strip()
+        elif in_suggestion and (line.startswith("Fix:") or line.startswith("fix:")):
+            current_suggestion["fix"] = line.split(":", 1)[1].strip()
+        elif in_suggestion and line.startswith("File:"):
+            current_suggestion["file_path"] = line.split(":", 1)[1].strip()
+    
+    if current_suggestion:
+        suggestions.append(current_suggestion)
+    
+    return suggestions
+
 @app.get("/health")
 async def health_check():
     return {"status": "healthy"}
````

## real-suggestions-endpoint

**5. real-bug, complex, python** · commit 467452c, backend/src/main.py (fixed in a448d6a)

- **major**: The 404 for a missing PR is raised inside the try block, so the broad `except Exception` catches it and returns a 500 instead (`backend/src/main.py` lines 378-383; `backend/src/main.py` lines 420-425)
- **major**: With API_KEY unset (it defaults to an empty string), authentication can be bypassed: a header of "Bearer " plus a character Python's strip() removes but HTTP servers don't (a non-breaking space, 0xA0) strips to "" and matches the empty key. Also compared with !=, not in constant time (`backend/src/main.py` lines 36-41; `backend/src/main.py` lines 74-74)

```diff
diff --git a/backend/src/main.py b/backend/src/main.py
index 8b29e1c..3212719 100644
--- a/backend/src/main.py
+++ b/backend/src/main.py
@@ -1,6 +1,8 @@
 import os
 import json
-from fastapi import FastAPI, Request, HTTPException, Header, Depends
+from dotenv import load_dotenv
+from fastapi import FastAPI, Request, HTTPException, Header, Depends, Security
+from fastapi.security import APIKeyHeader
 from fastapi.middleware.cors import CORSMiddleware
 import hmac
 import hashlib
@@ -12,10 +14,38 @@ import httpx
 import asyncio
 from database import get_db, create_pr, update_pr_status, init_db, create_suggestion
 
+# Load environment variables from .env file
+load_dotenv('/home/sgtwickool/repos/codemop/.env')
+
 # Configure logging
 logging.basicConfig(level=logging.INFO)
 logger = logging.getLogger(__name__)
 
+# API Key Security
+api_key_header = APIKeyHeader(name="Authorization", auto_error=False)
+
+async def get_api_key(api_key_header: str = Security(api_key_header)):
+    """Extract and validate API key from Authorization header"""
+    if not api_key_header:
+        raise HTTPException(
+            status_code=401,
+            detail="Authorization header missing"
+        )
+    
+    # Handle "Bearer " prefix
+    if api_key_header.startswith("Bearer "):
+        api_key = api_key_header[7:].strip()
+    else:
+        api_key = api_key_header.strip()
+    
+    if api_key != API_KEY:
+        raise HTTPException(
+            status_code=401,
+            detail="Invalid API key"
+        )
+    
+    return api_key
+
 app = FastAPI()
 
 # Initialize database on startup
@@ -39,6 +69,10 @@ GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
 AI_API_KEY = os.getenv("AI_API_KEY", "")
 AI_API_URL = os.getenv("AI_API_URL", "https://api.mistral.ai/v1/chat/completions")
 AI_MODEL = os.getenv("AI_MODEL", "codestral-latest")
+
+# API Authentication
+API_KEY = os.getenv("API_KEY", "")
+
 MAX_RETRIES = 3
 RETRY_DELAY = 1.0
 
@@ -319,6 +353,79 @@ def extract_suggestions_from_text(text: str) -> list:
     
     return suggestions
 
+@app.get("/pr/{pr_id}/suggestions")
+async def get_suggestions(
+    pr_id: int,
+    api_key: str = Depends(get_api_key)
+):
+    """
+    Get all suggestions for a specific PR
+    
+    Args:
+        pr_id: The database ID of the PR
+        api_key: Valid API key for authentication
+    
+    Returns:
+        List of suggestions with line numbers, descriptions, and fixes
+    """
+    db = next(get_db())
+    try:
+        # Import PR model here to avoid circular imports
+        from database import PR, Suggestion
+        
+        # First check if PR exists
+        pr = db.query(PR).filter(PR.id == pr_id).first()
+        if not pr:
+            raise HTTPException(
+                status_code=404,
+                detail=f"PR with ID {pr_id} not found"
+            )
+        
+        # Get all suggestions for this PR
+        suggestions = db.query(Suggestion).filter(Suggestion.pr_id == pr_id).all()
+        
+        if not suggestions:
+            return {
+                "pr_id": pr_id,
+                "github_id": pr.github_id,
+                "repo": pr.repo_full_name,
+                "title": pr.title,
+                "suggestions": [],
+                "message": "No suggestions found for this PR"
+            }
+        
+        # Format suggestions for API response
+        formatted_suggestions = []
+        for suggestion in suggestions:
+            formatted_suggestions.append({
+                "id": suggestion.id,
+                "line_number": suggestion.line_number,
+                "file_path": suggestion.file_path,
+                "description": suggestion.description,
+                "fix": suggestion.fix,
+                "confidence": suggestion.confidence,
+                "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None
+            })
+        
+        return {
+            "pr_id": pr_id,
+            "github_id": pr.github_id,
+            "repo": pr.repo_full_name,
+            "title": pr.title,
+            "status": pr.status,
+            "suggestions_count": len(formatted_suggestions),
+            "suggestions": formatted_suggestions
+        }
+        
+    except Exception as e:
+        logger.error(f"Error fetching suggestions for PR {pr_id}: {str(e)}")
+        raise HTTPException(
+            status_code=500,
+            detail=f"Error retrieving suggestions: {str(e)}"
+        )
+    finally:
+        db.close()
+
 @app.get("/health")
 async def health_check():
     return {"status": "healthy"}
```

## real-refactor-webhooks

**6. real-bug, complex, python** · commit 94162a3, webhooks.py and security.py (fixed in a448d6a)

- **major**: `pr_data` isn't defined in this function (it's pr_db_data / pr_metadata), so logging after storing suggestions, and in its error handler, raises NameError (`backend/src/app/api/v1/endpoints/webhooks.py` lines 69-71)
- **minor**: The webhook signature is only checked for pull_request events, not every event (`backend/src/app/api/v1/endpoints/webhooks.py` lines 21-23)

```diff
diff --git a/backend/src/app/api/v1/endpoints/webhooks.py b/backend/src/app/api/v1/endpoints/webhooks.py
new file mode 100644
index 0000000..7437d25
--- /dev/null
+++ b/backend/src/app/api/v1/endpoints/webhooks.py
@@ -0,0 +1,84 @@
+from fastapi import APIRouter, Request, HTTPException, Header
+from typing import Optional
+from app.services.github import validate_github_webhook_signature, extract_pr_data, extract_pr_metadata
+from app.services.pr_service import pr_service
+from app.services.suggestion_service import suggestion_service
+from app.services.ai_analysis import analyze_pr_with_ai
+from app.db.session import get_db
+import logging
+from datetime import datetime
+
+router = APIRouter()
+logger = logging.getLogger(__name__)
+
+@router.post("/github/webhook")
+async def handle_github_webhook(
+    request: Request,
+    x_github_event: Optional[str] = Header(None),
+    x_hub_signature_256: Optional[str] = Header(None)
+):
+    # Only validate webhook signature for pull_request events
+    if x_github_event == "pull_request":
+        request_body = await request.body()
+        await validate_github_webhook_signature(request_body, x_hub_signature_256)
+    
+    # Only process pull_request events
+    if x_github_event != "pull_request":
+        logger.info(f"Received non-PR event: {x_github_event}")
+        return {"status": "ignored", "reason": "not a pull_request event"}
+    
+    payload = await request.json()
+    
+    # Extract PR data for database
+    pr_db_data = extract_pr_data(payload)
+    
+    # Extract PR metadata for logging
+    pr_metadata = extract_pr_metadata(payload)
+    
+    logger.info(f"Processing PR #{pr_metadata['pr_number']} - Action: {pr_metadata['action']}")
+    logger.info(f"Repository: {pr_db_data['repo_full_name']}")
+    logger.info(f"PR Title: {pr_db_data['title']}")
+    logger.info(f"Author: {pr_db_data['author']}")
+    logger.info(f"Branch: {pr_db_data['branch']}")
+    
+    # Store PR data in database
+    db = next(get_db())
+    try:
+        pr_record = pr_service.create_pr(db, pr_db_data)
+    except Exception as e:
+        logger.error(f"Failed to store PR data: {str(e)}")
+        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
+    finally:
+        db.close()
+    
+    # Trigger AI analysis
+    suggestions = []
+    if pr_db_data.get("diff_url"):
+        try:
+            logger.info(f"Starting AI analysis for PR #{pr_metadata['pr_number']}")
+            suggestions = await analyze_pr_with_ai(pr_db_data.get("diff_url"))
+        except Exception as e:
+            logger.error(f"AI analysis failed for PR #{pr_metadata['pr_number']}: {str(e)}")
+            # Don't fail the entire webhook if AI analysis fails
+    
+    # Store suggestions in database
+    if suggestions:
+        db = next(get_db())
+        try:
+            suggestion_service.create_suggestions_batch(db, pr_record.id, suggestions)
+            logger.info(f"💾 Stored {len(suggestions)} suggestions for PR #{pr_data['pr_number']}")
+        except Exception as e:
+            logger.error(f"💾 Failed to store suggestions for PR #{pr_data['pr_number']}: {str(e)}")
+            # Don't fail the entire webhook if suggestion storage fails
+        finally:
+            db.close()
+    
+    return {
+        "status": "success",
+        "pr_number": pr_metadata['pr_number'],
+        "action": pr_metadata['action'],
+        "repository": pr_db_data['repo_full_name'],
+        "database_id": pr_record.id,
+        "suggestions_count": len(suggestions),
+        "timestamp": datetime.utcnow().isoformat()
+    }
\ No newline at end of file
diff --git a/backend/src/app/core/security.py b/backend/src/app/core/security.py
new file mode 100644
index 0000000..813c88e
--- /dev/null
+++ b/backend/src/app/core/security.py
@@ -0,0 +1,27 @@
+from fastapi import HTTPException, Security
+from fastapi.security import APIKeyHeader
+from app.config import settings
+
+api_key_header = APIKeyHeader(name="Authorization", auto_error=False)
+
+async def get_api_key(api_key_header: str = Security(api_key_header)):
+    """Extract and validate API key from Authorization header"""
+    if not api_key_header:
+        raise HTTPException(
+            status_code=401,
+            detail="Authorization header missing"
+        )
+    
+    # Handle "Bearer " prefix
+    if api_key_header.startswith("Bearer "):
+        api_key = api_key_header[7:].strip()
+    else:
+        api_key = api_key_header.strip()
+    
+    if api_key != settings.API_KEY:
+        raise HTTPException(
+            status_code=401,
+            detail="Invalid API key"
+        )
+    
+    return api_key
\ No newline at end of file
```

## real-security-config

**7. real-bug, complex, python, security** · commit df43463, security_config.py and main.py (fixed in 10683fd, a448d6a and 390dc03)

- **major**: CORS allows any origin together with credentials, which lets any website make credentialed requests to the API (`backend/src/app/core/security_config.py` lines 26-27)
- **minor**: Content-Security-Policy default-src 'self' blocks the CDN scripts and styles FastAPI's Swagger/ReDoc pages load, so the API docs render blank (`backend/src/app/core/security_config.py` lines 21-21)
- **minor**: A per-IP limit of 10 webhooks a minute: GitHub's deliveries come from a few shared IPs, so bursts get 429s, and GitHub doesn't retry those (`backend/src/app/core/security_config.py` lines 7-7)

```diff
diff --git a/backend/src/app/core/security_config.py b/backend/src/app/core/security_config.py
new file mode 100644
index 0000000..55a711e
--- /dev/null
+++ b/backend/src/app/core/security_config.py
@@ -0,0 +1,38 @@
+"""
+Security configuration and constants for the application.
+"""
+
+# Rate limit configurations
+RATE_LIMITS = {
+    "webhook": "10/minute",
+    "suggestions": "60/minute",
+    "health": "120/minute"
+}
+
+# Request size limits
+MAX_REQUEST_SIZE = 1024 * 1024  # 1MB
+
+# Security headers configuration
+SECURITY_HEADERS = {
+    "X-Content-Type-Options": "nosniff",
+    "X-Frame-Options": "DENY",
+    "X-XSS-Protection": "1; mode=block",
+    "Referrer-Policy": "strict-origin-when-cross-origin",
+    "Content-Security-Policy": "default-src 'self'"
+}
+
+# CORS configuration
+CORS_SETTINGS = {
+    "allow_origins": ["*"],
+    "allow_credentials": True,
+    "allow_methods": ["*"],
+    "allow_headers": ["*"],
+}
+
+# API security settings
+API_SECURITY = {
+    "default_rate_limit": "60/minute",
+    "max_request_size": MAX_REQUEST_SIZE,
+    "require_https": True,
+    "strict_transport_security": "max-age=31536000; includeSubDomains; preload"
+}
\ No newline at end of file
diff --git a/backend/src/app/main.py b/backend/src/app/main.py
index f5afdbc..c22c4a6 100644
--- a/backend/src/app/main.py
+++ b/backend/src/app/main.py
@@ -1,15 +1,24 @@
 from contextlib import asynccontextmanager
-from fastapi import FastAPI
+from fastapi import FastAPI, Request
 from fastapi.middleware.cors import CORSMiddleware
+from fastapi.responses import JSONResponse
+from slowapi import Limiter, _rate_limit_exceeded_handler
+from slowapi.util import get_remote_address
+from slowapi.errors import RateLimitExceeded
 from app.api.v1.api import api_router
 from app.db.session import init_db
 from app.config import settings
+from app.core.security_config import RATE_LIMITS, CORS_SETTINGS
+from app.core.security_middleware import limit_request_size, add_security_headers
 import logging
 
 # Configure logging
 logging.basicConfig(level=logging.INFO)
 logger = logging.getLogger(__name__)
 
+# Initialize rate limiter
+limiter = Limiter(key_func=get_remote_address)
+
 @asynccontextmanager
 async def lifespan(app: FastAPI):
     """FastAPI lifespan context manager (modern alternative to on_event)"""
@@ -29,15 +38,20 @@ app = FastAPI(
     openapi_url="/api/v1/openapi.json"
 )
 
-# CORS configuration
+# CORS configuration (using centralized config)
 app.add_middleware(
     CORSMiddleware,
-    allow_origins=["*"],
-    allow_credentials=True,
-    allow_methods=["*"],
-    allow_headers=["*"],
+    **CORS_SETTINGS
 )
 
+# Rate limiting configuration
+app.state.limiter = limiter
+app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
+
+# Security middleware (organized in separate module)
+app.middleware("http")(limit_request_size)
+app.middleware("http")(add_security_headers)
+
 # Include API router
 app.include_router(api_router, prefix="/api/v1")
 
```

## real-prod-dockerfile

**8. real-bug, complex, docker** · commit a3f6dcd, backend/Dockerfile.prod (fixed in a448d6a)

- **major**: The HEALTHCHECK uses curl, which python:slim images don't include, so the container never reports healthy (`backend/Dockerfile.prod` lines 48-49)
- **minor**: The runtime stage reinstalls every requirement from scratch, so the builder stage's install is wasted (the multi-stage build saves nothing) (`backend/Dockerfile.prod` lines 19-19; `backend/Dockerfile.prod` lines 42-42)

```diff
diff --git a/backend/Dockerfile.prod b/backend/Dockerfile.prod
new file mode 100644
index 0000000..aeb4433
--- /dev/null
+++ b/backend/Dockerfile.prod
@@ -0,0 +1,61 @@
+# Production Dockerfile for CodeMop
+# Uses multi-stage builds for optimization
+
+# Stage 1: Build stage
+FROM python:3.13-slim as builder
+
+# Install build dependencies
+RUN apt-get update && apt-get install -y \
+    build-essential \
+    && rm -rf /var/lib/apt/lists/*
+
+# Create and switch to a non-root user for security
+RUN useradd -m appuser
+USER appuser
+WORKDIR /app
+
+# Copy requirements first for better caching
+COPY --chown=appuser:appuser requirements.txt .
+RUN pip install --user -r requirements.txt
+
+# Copy application code
+COPY --chown=appuser:appuser . .
+
+# Stage 2: Runtime stage
+FROM python:3.13-slim
+
+# Install runtime dependencies
+RUN apt-get update && apt-get install -y \
+    libpq5 \
+    && rm -rf /var/lib/apt/lists/*
+
+# Create and switch to non-root user
+RUN useradd -m appuser
+USER appuser
+WORKDIR /app
+
+# Copy only necessary files from builder
+COPY --from=builder --chown=appuser:appuser /app/src /app/src
+COPY --from=builder --chown=appuser:appuser /app/requirements.txt .
+
+# Install only production dependencies
+RUN pip install --user --no-cache-dir -r requirements.txt
+
+# Add user's local bin to PATH
+ENV PATH=/home/appuser/.local/bin:$PATH
+
+# Health check (note: Podman uses OCI format, Docker uses Docker format)
+HEALTHCHECK --interval=30s --timeout=3s \
+    CMD curl -f http://localhost:8000/health || exit 1
+
+# Environment variables
+ENV PYTHONPATH=/app/src
+ENV PYTHONUNBUFFERED=1
+ENV APP_ENV=production
+ENV DEBUG=False
+
+# Expose port
+EXPOSE 8000
+
+# Run the application
+CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
\ No newline at end of file
```

## real-monitoring

**9. real-bug, complex, python** · commit fdb2b90, monitoring middleware and setup (fixed in 5435754)

- **major**: The middleware imports REQUEST_COUNT and the other metrics by value at import time, while they're still None (setup_metrics() assigns the module globals later), so no metrics are ever recorded (`backend/src/app/core/middleware/monitoring_middleware.py` lines 11-11; `backend/src/app/core/middleware/monitoring_middleware.py` lines 74-74; `backend/src/app/core/monitoring.py` lines 241-244)
- **minor**: A metrics HTTP server is started on a fixed port by default, at import time (`backend/src/app/core/monitoring.py` lines 188-190)

```diff
diff --git a/backend/src/app/core/middleware/monitoring_middleware.py b/backend/src/app/core/middleware/monitoring_middleware.py
new file mode 100644
index 0000000..b4bff20
--- /dev/null
+++ b/backend/src/app/core/middleware/monitoring_middleware.py
@@ -0,0 +1,100 @@
+"""
+Monitoring Middleware for CodeMop
+
+This module contains middleware for request monitoring and error tracking.
+"""
+
+from fastapi import Request
+from typing import Callable, Awaitable
+import time
+import logging
+from app.core.monitoring import REQUEST_COUNT, REQUEST_LATENCY, ACTIVE_REQUESTS, ERROR_COUNT
+
+logger = logging.getLogger(__name__)
+
+async def error_tracking_middleware(
+    request: Request,
+    call_next: Callable[[Request], Awaitable]
+) -> Awaitable:
+    """
+    Middleware to track errors and exceptions with context.
+    
+    Captures exceptions and logs them with request context,
+    updates error metrics, and re-raises the exception.
+    """
+    try:
+        response = await call_next(request)
+        return response
+    except Exception as exc:
+        # Log error with context
+        logger.error("Request failed", extra={
+            "error": str(exc),
+            "error_type": type(exc).__name__,
+            "method": request.method,
+            "path": request.url.path,
+            "user_agent": request.headers.get("user-agent", ""),
+            "remote_addr": request.client.host if request.client else ""
+        })
+        
+        # Update error metrics
+        if ERROR_COUNT:
+            ERROR_COUNT.labels(
+                error_type=type(exc).__name__,
+                endpoint=request.url.path
+            ).inc()
+        
+        # Re-raise the exception
+        raise
+
+async def request_monitoring_middleware(
+    request: Request,
+    call_next: Callable[[Request], Awaitable]
+) -> Awaitable:
+    """
+    Middleware to track request metrics and performance.
+    
+    Tracks request duration, updates Prometheus metrics,
+    and logs request completion with performance data.
+    """
+    start_time = time.time()
+    
+    # Increment active requests counter
+    if ACTIVE_REQUESTS:
+        ACTIVE_REQUESTS.inc()
+    
+    try:
+        response = await call_next(request)
+        return response
+    finally:
+        # Calculate request duration
+        duration = time.time() - start_time
+        status_code = getattr(response, "status_code", 500)
+        
+        # Update metrics
+        if REQUEST_COUNT:
+            REQUEST_COUNT.labels(
+                method=request.method,
+                endpoint=request.url.path,
+                status_code=status_code
+            ).inc()
+        
+        if REQUEST_LATENCY:
+            REQUEST_LATENCY.labels(
+                method=request.method,
+                endpoint=request.url.path
+            ).observe(duration)
+        
+        if ACTIVE_REQUESTS:
+            ACTIVE_REQUESTS.dec()
+        
+        # Log request completion
+        logger.info("Request completed", extra={
+            "method": request.method,
+            "path": request.url.path,
+            "status_code": status_code,
+            "duration_ms": duration * 1000,
+            "user_agent": request.headers.get("user-agent", ""),
+            "remote_addr": request.client.host if request.client else ""
+        })
+
+__all__ = ["error_tracking_middleware", "request_monitoring_middleware"]
\ No newline at end of file
diff --git a/backend/src/app/core/monitoring.py b/backend/src/app/core/monitoring.py
new file mode 100644
index 0000000..1cb2996
--- /dev/null
+++ b/backend/src/app/core/monitoring.py
@@ -0,0 +1,244 @@
+"""
+Monitoring and Observability Setup for CodeMop
+
+This module provides:
+- Structured JSON logging
+- Error tracking integration (Sentry)
+- Performance monitoring
+- Health metrics
+"""
+
+import logging
+import logging.config
+from typing import Optional, Dict, Any
+from datetime import datetime
+import time
+from functools import wraps
+from pythonjsonlogger import jsonlogger
+import os
+
+# Environment variables for monitoring configuration
+SENTRY_DSN = os.getenv("SENTRY_DSN", "")
+LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
+SERVICE_NAME = os.getenv("SERVICE_NAME", "codemop")
+ENVIRONMENT = os.getenv("APP_ENV", "development")
+
+class CustomJsonFormatter(jsonlogger.JsonFormatter):
+    """
+    Custom JSON formatter that adds additional context to logs
+    """
+    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
+        super().add_fields(log_record, record, message_dict)
+        
+        # Add custom fields
+        log_record["service"] = SERVICE_NAME
+        log_record["environment"] = ENVIRONMENT
+        log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"
+        
+        # Add request context if available
+        if hasattr(record, "request_id"):
+            log_record["request_id"] = record.request_id
+        if hasattr(record, "user_id"):
+            log_record["user_id"] = record.user_id
+        if hasattr(record, "endpoint"):
+            log_record["endpoint"] = record.endpoint
+
+def setup_logging() -> None:
+    """
+    Set up structured JSON logging for the application
+    """
+    # Configure JSON logging
+    log_handler = logging.StreamHandler()
+    formatter = CustomJsonFormatter(
+        fmt="%(timestamp)s %(levelname)s %(service)s %(environment)s %(message)s %(name)s"
+    )
+    log_handler.setFormatter(formatter)
+    
+    # Get root logger and configure it
+    root_logger = logging.getLogger()
+    root_logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
+    root_logger.handlers.clear()  # Remove any existing handlers
+    root_logger.addHandler(log_handler)
+    
+    # Configure specific loggers
+    logging.getLogger("uvicorn").handlers.clear()
+    logging.getLogger("uvicorn").addHandler(log_handler)
+    logging.getLogger("uvicorn").setLevel(logging.INFO)
+    
+    logging.getLogger("sqlalchemy").handlers.clear()
+    logging.getLogger("sqlalchemy").addHandler(log_handler)
+    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
+    
+    logging.getLogger("httpx").handlers.clear()
+    logging.getLogger("httpx").addHandler(log_handler)
+    logging.getLogger("httpx").setLevel(logging.WARNING)
+    
+    # Log the configuration
+    logger = logging.getLogger(__name__)
+    logger.info("Logging configured", extra={
+        "log_level": LOG_LEVEL,
+        "service": SERVICE_NAME,
+        "environment": ENVIRONMENT,
+        "sentry_enabled": bool(SENTRY_DSN)
+    })
+
+def setup_error_tracking() -> None:
+    """
+    Set up error tracking with Sentry (if configured)
+    """
+    if not SENTRY_DSN:
+        logging.getLogger(__name__).info("Sentry DSN not configured, error tracking disabled")
+        return
+    
+    try:
+        import sentry_sdk
+        from sentry_sdk.integrations.fastapi import FastApiIntegration
+        from sentry_sdk.integrations.logging import LoggingIntegration
+        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
+        
+        sentry_logging = LoggingIntegration(
+            level=logging.INFO,        # Capture info and above
+            event_level=logging.ERROR  # Send errors as events
+        )
+        
+        sentry_sdk.init(
+            dsn=SENTRY_DSN,
+            integrations=[
+                FastApiIntegration(),
+                LoggingIntegration(),
+                SqlalchemyIntegration(),
+            ],
+            traces_sample_rate=1.0 if ENVIRONMENT == "development" else 0.1,
+            environment=ENVIRONMENT,
+            release=os.getenv("GIT_COMMIT", "dev"),
+            server_name=os.getenv("HOSTNAME", "unknown")
+        )
+        
+        # Set up Sentry context processors
+        sentry_sdk.set_tag("service", SERVICE_NAME)
+        sentry_sdk.set_tag("environment", ENVIRONMENT)
+        
+        logging.getLogger(__name__).info("Sentry error tracking initialized")
+        
+    except ImportError:
+        logging.getLogger(__name__).warning("Sentry SDK not installed, error tracking disabled")
+    except Exception as e:
+        logging.getLogger(__name__).error(f"Failed to initialize Sentry: {e}")
+
+class PerformanceMonitor:
+    """
+    Context manager for monitoring function performance
+    """
+    def __init__(self, name: str, logger: Optional[logging.Logger] = None):
+        self.name = name
+        self.logger = logger or logging.getLogger(__name__)
+        self.start_time = None
+        self.end_time = None
+    
+    def __enter__(self):
+        self.start_time = time.time()
+        return self
+    
+    def __exit__(self, exc_type, exc_val, exc_tb):
+        self.end_time = time.time()
+        duration = self.end_time - self.start_time
+        
+        log_data = {
+            "operation": self.name,
+            "duration_ms": duration * 1000,
+            "success": exc_type is None
+        }
+        
+        if exc_type:
+            log_data["error"] = str(exc_val)
+            self.logger.error(f"Performance: {self.name} failed", extra=log_data)
+        else:
+            self.logger.info(f"Performance: {self.name} completed", extra=log_data)
+
+def monitor_endpoint(operation_name: str = None):
+    """
+    Decorator to monitor endpoint performance
+    """
+    def decorator(func):
+        @wraps(func)
+        async def wrapper(*args, **kwargs):
+            start_time = time.time()
+            try:
+                result = await func(*args, **kwargs)
+                return result
+            finally:
+                duration = time.time() - start_time
+                logger = logging.getLogger(func.__module__)
+                logger.info(f"Endpoint performance: {operation_name or func.__name__}", extra={
+                    "duration_ms": duration * 1000,
+                    "endpoint": operation_name or func.__name__
+                })
+        return wrapper
+    return decorator
+
+def setup_metrics() -> None:
+    """
+    Set up Prometheus metrics (if configured)
+    """
+    try:
+        from prometheus_client import start_http_server, Counter, Gauge, Histogram
+        from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST
+        
+        # Only start metrics server in production or if explicitly enabled
+        if os.getenv("ENABLE_METRICS", "true").lower() == "true":
+            metrics_port = int(os.getenv("METRICS_PORT", "8001"))
+            start_http_server(metrics_port)
+            
+            # Define custom metrics
+            global REQUEST_COUNT, REQUEST_LATENCY, ACTIVE_REQUESTS, ERROR_COUNT
+            
+            REQUEST_COUNT = Counter(
+                'codemop_requests_total',
+                'Total HTTP Requests',
+                ['method', 'endpoint', 'status_code']
+            )
+            
+            REQUEST_LATENCY = Histogram(
+                'codemop_request_latency_seconds',
+                'Request latency in seconds',
+                ['method', 'endpoint']
+            )
+            
+            ACTIVE_REQUESTS = Gauge(
+                'codemop_active_requests',
+                'Number of active requests'
+            )
+            
+            ERROR_COUNT = Counter(
+                'codemop_errors_total',
+                'Total Errors',
+                ['error_type', 'endpoint']
+            )
+            
+            logging.getLogger(__name__).info(f"Metrics server started on port {metrics_port}")
+        else:
+            logging.getLogger(__name__).info("Metrics disabled by configuration")
+            
+    except ImportError:
+        logging.getLogger(__name__).warning("Prometheus client not installed, metrics disabled")
+    except Exception as e:
+        logging.getLogger(__name__).error(f"Failed to initialize metrics: {e}")
+
+def setup_monitoring() -> None:
+    """
+    Set up all monitoring components
+    """
+    setup_logging()
+    setup_error_tracking()
+    setup_metrics()
+    
+    logger = logging.getLogger(__name__)
+    logger.info("Monitoring setup completed", extra={
+        "components": ["logging", "error_tracking", "metrics"]
+    })
+
+# Initialize metrics variables (will be set by setup_metrics)
+REQUEST_COUNT = None
+REQUEST_LATENCY = None
+ACTIVE_REQUESTS = None
+ERROR_COUNT = None
\ No newline at end of file
diff --git a/backend/src/app/main.py b/backend/src/app/main.py
index c22c4a6..119b339 100644
--- a/backend/src/app/main.py
+++ b/backend/src/app/main.py
@@ -9,11 +9,12 @@ from app.api.v1.api import api_router
 from app.db.session import init_db
 from app.config import settings
 from app.core.security_config import RATE_LIMITS, CORS_SETTINGS
-from app.core.security_middleware import limit_request_size, add_security_headers
+from app.core.middleware import error_tracking_middleware, request_monitoring_middleware, limit_request_size, add_security_headers
+from app.core.monitoring import setup_monitoring
 import logging
 
-# Configure logging
-logging.basicConfig(level=logging.INFO)
+# Initialize monitoring system
+setup_monitoring()
 logger = logging.getLogger(__name__)
 
 # Initialize rate limiter
@@ -48,6 +49,10 @@ app.add_middleware(
 app.state.limiter = limiter
 app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
 
+# Add monitoring middleware
+app.middleware("http")(error_tracking_middleware)
+app.middleware("http")(request_monitoring_middleware)
+
 # Security middleware (organized in separate module)
 app.middleware("http")(limit_request_size)
 app.middleware("http")(add_security_headers)
```

## seeded-pagination

**10. seeded-bug, simple, python**

- **major**: Pages are numbered from 1, but start = page * page_size, so page 1 skips the first page of results (`api/listing.py` lines 3-4)

```diff
diff --git a/api/listing.py b/api/listing.py
--- a/api/listing.py
+++ b/api/listing.py
@@ -1,3 +1,4 @@
-def list_orders(orders, page_size=20):
-    """Return the first page of orders"""
-    return orders[:page_size]
+def list_orders(orders, page=1, page_size=20):
+    """Return one page of orders; pages are numbered from 1"""
+    start = page * page_size
+    return orders[start:start + page_size]
```

## seeded-sql-injection

**11. seeded-bug, simple, python, security**

- **major**: name_fragment is interpolated into the SQL with an f-string: SQL injection (`store/users.py` lines 10-12)

```diff
diff --git a/store/users.py b/store/users.py
--- a/store/users.py
+++ b/store/users.py
@@ -2,3 +2,12 @@
     cur = conn.cursor()
     cur.execute("SELECT id, email FROM users WHERE email = %s", (email,))
     return cur.fetchone()
+
+
+def search_users(conn, name_fragment, limit=50):
+    """Users whose name contains `name_fragment`"""
+    cur = conn.cursor()
+    cur.execute(
+        f"SELECT id, name FROM users WHERE name ILIKE '%{name_fragment}%' LIMIT {int(limit)}"
+    )
+    return cur.fetchall()
```

## seeded-missing-await

**12. seeded-bug, simple, python**

- **major**: cache.set is async (cache.get is awaited) but isn't awaited, so the profile is never cached (`services/profile.py` lines 6-6)

```diff
diff --git a/services/profile.py b/services/profile.py
--- a/services/profile.py
+++ b/services/profile.py
@@ -2,4 +2,6 @@
     cached = await cache.get(f"profile:{user_id}")
     if cached:
         return cached
-    return await db.fetch_profile(user_id)
+    profile = await db.fetch_profile(user_id)
+    cache.set(f"profile:{user_id}", profile, ttl=300)
+    return profile
```

## seeded-mutable-default

**13. seeded-bug, simple, python**

- **major**: A mutable default argument: the same list is shared across calls and grows each time (`notify/email.py` lines 1-3)

```diff
diff --git a/notify/email.py b/notify/email.py
--- a/notify/email.py
+++ b/notify/email.py
@@ -1,2 +1,4 @@
-def build_message(subject, body):
-    return {"subject": subject, "body": body}
+def build_message(subject, body, recipients=[]):
+    """A message for `recipients`, always copying in the on-call address"""
+    recipients.append("oncall@example.com")
+    return {"subject": subject, "body": body, "to": recipients}
```

## seeded-async-foreach

**14. seeded-bug, simple, typescript**

- **major**: forEach doesn't await async callbacks, so syncAll returns 0 before any account is synced (`src/sync.ts` lines 3-7)

```diff
diff --git a/src/sync.ts b/src/sync.ts
--- a/src/sync.ts
+++ b/src/sync.ts
@@ -1,3 +1,8 @@
 export async function syncAll(accounts: Account[]): Promise<number> {
-  return 0;
+  let synced = 0;
+  accounts.forEach(async (account) => {
+    await syncAccount(account);
+    synced += 1;
+  });
+  return synced;
 }
```

## seeded-go-defer-before-err

**15. seeded-bug, simple, go**

- **major**: resp.Body.Close() is deferred before err is checked; when the request fails resp is nil and it panics (`client/fetch.go` lines 6-9)

```diff
diff --git a/client/fetch.go b/client/fetch.go
--- a/client/fetch.go
+++ b/client/fetch.go
@@ -3,5 +3,10 @@
 import "net/http"
 
 func Status(url string) (int, error) {
-	return 0, nil
+	resp, err := http.Get(url)
+	defer resp.Body.Close()
+	if err != nil {
+		return 0, err
+	}
+	return resp.StatusCode, nil
 }
```

## seeded-inverted-expiry

**16. seeded-bug, simple, python, security**

- **major**: The comparison is inverted: tokens are rejected while still valid, and accepted after they expire (`auth/tokens.py` lines 11-12)

```diff
diff --git a/auth/tokens.py b/auth/tokens.py
--- a/auth/tokens.py
+++ b/auth/tokens.py
@@ -7,4 +7,6 @@
 
 def check_token(token):
     """Raise TokenExpired if the token can no longer be used"""
-    pass
+    now = datetime.now(timezone.utc)
+    if token.expires_at > now:
+        raise TokenExpired(f"token {token.id} expired at {token.expires_at}")
```

## seeded-assignment-in-condition

**17. seeded-bug, simple, typescript, security**

- **major**: user.role = "admin" assigns rather than compares, so the check always passes and anyone can delete any project (`src/admin.ts` lines 5-5)

```diff
diff --git a/src/admin.ts b/src/admin.ts
--- a/src/admin.ts
+++ b/src/admin.ts
@@ -1,3 +1,9 @@
 export function canDeleteProject(user: User, project: Project): boolean {
+  if (project.ownerId === user.id) {
+    return true;
+  }
+  if (user.role = "admin") {
+    return true;
+  }
   return false;
 }
```

## seeded-regex-prefix-validation

**18. seeded-bug, simple, python, security**

- **major**: re.match only checks the start of the name (no end anchor), so a name like "db; rm -rf /" passes validation, and the command runs through a shell: command injection (`ops/backup.py` lines 7-9)

```diff
diff --git a/ops/backup.py b/ops/backup.py
--- a/ops/backup.py
+++ b/ops/backup.py
@@ -1,5 +1,9 @@
+import re
 import subprocess
 
 
 def backup(database):
-    subprocess.run(["pg_dump", "--file", "/backups/latest.sql", database], check=True)
+    """Back up one database to /backups/<database>.sql"""
+    if not re.match(r"[a-z_]+", database):
+        raise ValueError(f"invalid database name: {database!r}")
+    subprocess.run(f"pg_dump --file /backups/{database}.sql {database}", shell=True, check=True)
```

## cross-file-arg-order

**19. seeded-bug, complex, python, cross-file**

- **major**: transfer's arguments are reordered (amount moved last), but billing/invoices.py still calls transfer(invoice.total, customer.account, shop.account), so it passes the amount as the source account (`payments/ledger.py` lines 8-10)

```diff
diff --git a/payments/ledger.py b/payments/ledger.py
--- a/payments/ledger.py
+++ b/payments/ledger.py
@@ -5,8 +5,9 @@
     pass
 
 
-def transfer(amount, source: Account, target: Account):
-    """Move `amount` (in cents) from one account to another"""
+def transfer(source: Account, target: Account, amount: int):
+    """Move `amount` (in cents) from one account to another (accounts first, like the rest of
+    the ledger)"""
     if source.balance < amount:
         raise InsufficientFunds(source.id)
     source.balance -= amount
```

## cross-file-none-instead-of-raise

**20. seeded-bug, complex, python, cross-file**

- **major**: find_user now returns None for an unknown email instead of raising UserNotFound, but api/login.py still catches UserNotFound and then calls user.check_password, so logging in with an unknown email crashes (AttributeError, a 500) instead of answering 401 (`accounts/users.py` lines 19-23)

```diff
diff --git a/accounts/users.py b/accounts/users.py
--- a/accounts/users.py
+++ b/accounts/users.py
@@ -1,4 +1,5 @@
 from dataclasses import dataclass
+from typing import Optional
 
 
 class UserNotFound(Exception):
@@ -15,9 +16,9 @@
         return hasher.verify(password, self.password_hash)
 
 
-def find_user(db, email):
-    """The user with this email address"""
-    row = db.fetch_one("SELECT id, email, password_hash FROM users WHERE email = ?", (email,))
+def find_user(db, email) -> Optional["User"]:
+    """The user with this email address, or None if there isn't one"""
+    row = db.fetch_one("SELECT id, email, password_hash FROM users WHERE email = ?", (email.lower(),))
     if row is None:
-        raise UserNotFound(email)
+        return None
     return User(**row)
```

## cross-file-units

**21. seeded-bug, complex, python, cross-file, security**

- **major**: SESSION_TIMEOUT is now in seconds (1800), but auth/sessions.py still uses it as minutes (timedelta(minutes=SESSION_TIMEOUT)), so sessions last 30 hours instead of 30 minutes (`config/settings.py` lines 4-5)

```diff
diff --git a/config/settings.py b/config/settings.py
--- a/config/settings.py
+++ b/config/settings.py
@@ -1,5 +1,6 @@
 import os
 
 DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")
-SESSION_TIMEOUT = 30  # minutes
+# Timeouts, all in seconds
+SESSION_TIMEOUT = 30 * 60
 REQUEST_TIMEOUT = 10
```

## cross-file-sync-to-async

**22. seeded-bug, complex, python, cross-file**

- **major**: load_flags is now async, but web/views.py still calls it without await from a plain function, so flags is a coroutine and flags.get raises AttributeError: the home page breaks (`features/flags.py` lines 6-6)

```diff
diff --git a/features/flags.py b/features/flags.py
--- a/features/flags.py
+++ b/features/flags.py
@@ -1,10 +1,11 @@
-import requests
+import httpx
 
 FLAGS_URL = "https://flags.internal/api/flags"
 
 
-def load_flags():
+async def load_flags():
     """The feature flags for this deployment"""
-    response = requests.get(FLAGS_URL, timeout=5)
+    async with httpx.AsyncClient(timeout=5) as client:
+        response = await client.get(FLAGS_URL)
     response.raise_for_status()
     return response.json()
```

## cross-file-renamed-key

**23. seeded-bug, complex, python, cross-file**

- **major**: The customer_id key is renamed to customerId, but jobs/receipts.py still reads data["customer_id"], so sending a receipt raises KeyError (`orders/serialize.py` lines 5-5)

```diff
diff --git a/orders/serialize.py b/orders/serialize.py
--- a/orders/serialize.py
+++ b/orders/serialize.py
@@ -1,8 +1,8 @@
 def order_to_dict(order):
-    """An order as JSON, for the API and the background jobs"""
+    """An order as JSON, for the API and the background jobs (camelCase, for the web app)"""
     return {
         "id": order.id,
-        "customer_id": order.customer_id,
+        "customerId": order.customer_id,
         "total": order.total,
         "items": [{"sku": item.sku, "quantity": item.quantity} for item in order.items],
     }
```

## clean-rename-refactor

**24. clean, simple, python**

Expected: nothing wrong.

```diff
diff --git a/billing/invoice.py b/billing/invoice.py
--- a/billing/invoice.py
+++ b/billing/invoice.py
@@ -1,5 +1,3 @@
-def calc(items):
-    t = 0
-    for i in items:
-        t += i.price * i.qty
-    return t
+def invoice_total(items):
+    """The sum of price * quantity over the invoice's line items"""
+    return sum(item.price * item.qty for item in items)
```

## clean-add-tests

**25. clean, simple, python**

Expected: nothing wrong.

```diff
diff --git a/tests/test_slugify.py b/tests/test_slugify.py
new file mode 100644
--- /dev/null
+++ b/tests/test_slugify.py
@@ -0,0 +1,17 @@
+import pytest
+
+from textutil import slugify
+
+
+@pytest.mark.parametrize("title, slug", [
+    ("Hello World", "hello-world"),
+    ("  Trim me  ", "trim-me"),
+    ("Already-slugged", "already-slugged"),
+    ("Symbols & stuff!", "symbols-stuff"),
+])
+def test_slugify(title, slug):
+    assert slugify(title) == slug
+
+
+def test_empty_title():
+    assert slugify("") == ""
```

## clean-docs

**26. clean, simple, docs**

Expected: nothing wrong.

```diff
diff --git a/docs/deploying.md b/docs/deploying.md
--- a/docs/deploying.md
+++ b/docs/deploying.md
@@ -1,3 +1,7 @@
 # Deploying
 
-Run `make deploy`.
+1. Make sure CI is green on `main`.
+2. Run `make deploy ENV=staging` and check the staging site.
+3. Run `make deploy ENV=production`.
+
+If a deploy fails, `make rollback ENV=production` restores the previous release.
```

## clean-small-feature

**27. clean, simple, python**

Expected: nothing wrong.

```diff
diff --git a/geo/distance.py b/geo/distance.py
--- a/geo/distance.py
+++ b/geo/distance.py
@@ -1,6 +1,7 @@
 import math
 
 EARTH_RADIUS_KM = 6371.0
+KM_PER_MILE = 1.609344
 
 
 def haversine_km(lat1, lon1, lat2, lon2):
@@ -10,3 +11,8 @@
     dlmb = math.radians(lon2 - lon1)
     a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
     return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
+
+
+def haversine_miles(lat1, lon1, lat2, lon2):
+    """Great-circle distance between two points, in miles"""
+    return haversine_km(lat1, lon1, lat2, lon2) / KM_PER_MILE
```

## clean-real-placement

**28. clean, complex, python** · commit 495398d, src/codemop/review/placement.py

Expected: nothing wrong.

```diff
diff --git a/src/codemop/review/placement.py b/src/codemop/review/placement.py
new file mode 100644
index 0000000..b159565
--- /dev/null
+++ b/src/codemop/review/placement.py
@@ -0,0 +1,44 @@
+"""
+Checking that each suggestion points at lines GitHub can comment on.
+
+A review comment has to be on an added or unchanged line shown in the diff; a model that
+points elsewhere (a removed line, a line outside the hunks, a file it wasn't shown) has
+made a mistake, and that suggestion is set aside rather than posted in the wrong place.
+"""
+from dataclasses import dataclass
+from typing import Dict, List, Sequence, Set
+
+from codemop.review.diff import FileDiff
+from codemop.review.schema import ModelSuggestion
+
+
+@dataclass(frozen=True)
+class Unplaced:
+    suggestion: ModelSuggestion
+    reason: str
+
+
+@dataclass
+class Placement:
+    placed: List[ModelSuggestion]
+    unplaced: List[Unplaced]
+
+
+def place_suggestions(suggestions: Sequence[ModelSuggestion], files: Sequence[FileDiff]) -> Placement:
+    """Split suggestions into those on commentable lines and those that aren't"""
+    commentable: Dict[str, Set[int]] = {file.path: file.commentable_lines() for file in files}
+    placed: List[ModelSuggestion] = []
+    unplaced: List[Unplaced] = []
+
+    for suggestion in suggestions:
+        lines = commentable.get(suggestion.file_path)
+        end_line = suggestion.end_line or suggestion.line
+        if lines is None:
+            unplaced.append(Unplaced(suggestion, "file isn't in the reviewed diff"))
+        elif end_line < suggestion.line:
+            unplaced.append(Unplaced(suggestion, "end_line is before line"))
+        elif not set(range(suggestion.line, end_line + 1)) <= lines:
+            unplaced.append(Unplaced(suggestion, "lines aren't added or unchanged lines in the diff"))
+        else:
+            placed.append(suggestion)
+    return Placement(placed=placed, unplaced=unplaced)
```

## clean-real-pricing

**29. clean, simple, python** · commit a82f899, src/codemop/providers/pricing.py

Expected: nothing wrong.

```diff
diff --git a/src/codemop/providers/pricing.py b/src/codemop/providers/pricing.py
new file mode 100644
index 0000000..9765e90
--- /dev/null
+++ b/src/codemop/providers/pricing.py
@@ -0,0 +1,45 @@
+"""
+Estimating what a review cost, from list prices.
+
+Prices change, so these are dated and the result is always described as an estimate. A model
+without a known price gets no estimate rather than a guess.
+"""
+from dataclasses import dataclass
+from typing import Dict, Optional
+
+from codemop.providers.base import Usage
+
+PRICES_AS_OF = "2026-09-25"
+
+
+@dataclass(frozen=True)
+class Price:
+    """US dollars per million tokens"""
+    input: float
+    output: float
+    cache_read: Optional[float] = None  # default: a tenth of the input price
+
+    def cost(self, usage: Usage) -> float:
+        cache_read = self.cache_read if self.cache_read is not None else self.input / 10
+        return (
+            usage.input_tokens * self.input
+            + usage.output_tokens * self.output
+            + usage.cache_read_tokens * cache_read
+            + usage.cache_write_tokens * self.input * 1.25  # five-minute cache writes
+        ) / 1_000_000
+
+
+# Anthropic list prices on the Claude API
+ANTHROPIC_PRICES: Dict[str, Price] = {
+    "claude-fable-5-1": Price(10.00, 50.00, cache_read=0.25),
+    "claude-fable-5": Price(10.00, 50.00),
+    "claude-opus-5-5": Price(4.00, 20.00, cache_read=0.20),
+    "claude-opus-5": Price(5.00, 25.00),
+    "claude-opus-4-8": Price(5.00, 25.00),
+    "claude-opus-4-7": Price(5.00, 25.00),
+    "claude-opus-4-6": Price(5.00, 25.00),
+    "claude-sonnet-5-5": Price(2.00, 10.00, cache_read=0.20),
+    "claude-sonnet-5": Price(2.00, 10.00),
+    "claude-sonnet-4-6": Price(3.00, 15.00),
+    "claude-haiku-4-5": Price(1.00, 5.00),
+}
```

## clean-real-github-client

**30. clean, complex, python** · commit 576d45f, src/codemop/github/client.py

Expected: nothing wrong.

```diff
diff --git a/src/codemop/github/client.py b/src/codemop/github/client.py
new file mode 100644
index 0000000..4b9dcf6
--- /dev/null
+++ b/src/codemop/github/client.py
@@ -0,0 +1,77 @@
+"""
+Fetching pull request diffs from the GitHub REST API.
+
+Uses a token when one is given, which private repositories need (and which raises the
+rate limit from 60 to 5,000 requests an hour for public ones).
+"""
+import re
+from dataclasses import dataclass
+from typing import Optional
+
+import httpx
+
+DEFAULT_API_URL = "https://api.github.com"
+
+_PR_REFERENCE = re.compile(r"^(?P<repo>[\w.-]+/[\w.-]+)#(?P<number>\d+)$")
+_PR_URL = re.compile(r"^https?://[^/]+/(?P<repo>[\w.-]+/[\w.-]+)/pull/(?P<number>\d+)(?:[/?#].*)?$")
+
+
+class GitHubError(Exception):
+    """A GitHub request failed; the message says what to do about it"""
+
+
+@dataclass(frozen=True)
+class PullRequestRef:
+    repo: str  # owner/name
+    number: int
+
+    def __str__(self) -> str:
+        return f"{self.repo}#{self.number}"
+
+
+def parse_pr_reference(text: str) -> PullRequestRef:
+    """owner/repo#123, or a PR URL like https://github.com/owner/repo/pull/123"""
+    match = _PR_REFERENCE.match(text.strip()) or _PR_URL.match(text.strip())
+    if not match:
+        raise ValueError(f"Not a pull request: {text!r} (use owner/repo#123 or a PR URL)")
+    return PullRequestRef(match.group("repo"), int(match.group("number")))
+
+
+def _error_message(status: int, body: str, pr: PullRequestRef, has_token: bool) -> str:
+    if status == 401:
+        return f"GitHub rejected the token while fetching {pr}; check it's valid and hasn't expired"
+    if status == 403 and "rate limit" in body.lower():
+        hint = "" if has_token else "; set GITHUB_TOKEN (or log in with `gh auth login`) for a higher limit"
+        return f"GitHub API rate limit reached while fetching {pr}{hint}"
+    if status in (403, 404):
+        if has_token:
+            return (f"GitHub returned {status} for {pr}: the token needs read access to this "
+                    "repository's pull requests and contents")
+        return (f"GitHub returned {status} for {pr}: if the repository is private, set "
+                "GITHUB_TOKEN (or log in with `gh auth login`)")
+    if status == 406:
+        return f"The diff for {pr} is too large for the GitHub API to return"
+    return f"GitHub returned {status} while fetching the diff for {pr}"
+
+
+async def fetch_pr_diff(
+    pr: PullRequestRef,
+    *,
+    token: Optional[str] = None,
+    api_url: str = DEFAULT_API_URL,
+    transport: Optional[httpx.AsyncBaseTransport] = None,
+) -> str:
+    """The PR's diff, from GET /repos/{owner}/{repo}/pulls/{number} as application/vnd.github.diff"""
+    headers = {"Accept": "application/vnd.github.diff", "X-GitHub-Api-Version": "2022-11-28"}
+    if token:
+        headers["Authorization"] = f"Bearer {token}"
+    url = f"{api_url.rstrip('/')}/repos/{pr.repo}/pulls/{pr.number}"
+
+    async with httpx.AsyncClient(headers=headers, timeout=60.0, transport=transport) as client:
+        try:
+            response = await client.get(url)
+        except httpx.TransportError:
+            raise GitHubError(f"Couldn't connect to {api_url}; check the network")
+    if response.status_code != 200:
+        raise GitHubError(_error_message(response.status_code, response.text, pr, bool(token)))
+    return response.text
```

## clean-cross-file-optional-argument

**31. clean, complex, python, cross-file**

Expected: nothing wrong.

```diff
diff --git a/notify/email.py b/notify/email.py
--- a/notify/email.py
+++ b/notify/email.py
@@ -1,4 +1,6 @@
-def send_email(smtp, to, subject, body):
-    """Send a plain-text email"""
-    message = f"To: {to}\nSubject: {subject}\n\n{body}"
-    smtp.sendmail("noreply@example.com", [to], message)
+def send_email(smtp, to, subject, body, reply_to=None):
+    """Send a plain-text email, with a Reply-To address if there's one"""
+    headers = f"To: {to}\nSubject: {subject}\n"
+    if reply_to:
+        headers += f"Reply-To: {reply_to}\n"
+    smtp.sendmail("noreply@example.com", [to], f"{headers}\n{body}")
```

## clean-cross-file-generator

**32. clean, complex, python, cross-file**

Expected: nothing wrong.

```diff
diff --git a/reports/users.py b/reports/users.py
--- a/reports/users.py
+++ b/reports/users.py
@@ -1,3 +1,3 @@
 def active_users(db):
-    """Every user who has logged in during the last 30 days"""
-    return [row for row in db.query("SELECT * FROM users WHERE last_login > now() - interval '30 days'")]
+    """Every user who has logged in during the last 30 days, a row at a time (there are millions)"""
+    yield from db.stream("SELECT * FROM users WHERE last_login > now() - interval '30 days'")
```
