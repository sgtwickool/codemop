Here’s a **detailed breakdown of Epic 1: Core Backend & Git Integration**, including **user stories, acceptance criteria, and technical details** to get you started:

---

## **Epic 1: Core Backend & Git Integration**
**Goal**: Build a minimal backend that integrates with GitHub, receives PR events via webhooks, and provides AI-powered suggestions.

---

### **User Story 1: GitHub Webhook Integration**
**As a developer, I want codemop to automatically analyze my PRs when opened, so I can get immediate feedback.**

#### **Acceptance Criteria**
1. **Webhook Setup**:
   - Codemop backend listens for GitHub webhook events (e.g., `pull_request`).
   - Webhook is configured via GitHub’s UI (or programmatically).
   - Events are logged in the backend (e.g., "PR #123 opened in repo `gregs-org/test-repo`").

2. **PR Data Handling**:
   - Extract PR details (e.g., repo, branch, author, diff).
   - Store PR metadata in PostgreSQL (e.g., `pr_id`, `repo_name`, `status`).

3. **Security**:
   - Validate webhook signatures to ensure requests are from GitHub.
   - Reject non-PR events (e.g., `push`, `issue_comment`).

#### **Technical Details**
- **GitHub Webhook Setup**:
  - Use [GitHub’s webhook docs](https://docs.github.com/en/developers/webhooks-and-events/webhooks/about-webhooks) to configure the webhook URL (e.g., `https://codemop-backend.com/github/webhook`).
  - Test with a tool like [ngrok](https://ngrok.com/) to expose your local backend to GitHub.

- **Database Schema**:
  ```sql
  CREATE TABLE prs (
      id SERIAL PRIMARY KEY,
      github_id INTEGER NOT NULL,
      repo_name VARCHAR(255) NOT NULL,
      branch VARCHAR(255) NOT NULL,
      author VARCHAR(255) NOT NULL,
      status VARCHAR(50) NOT NULL,  -- "open", "closed", "merged"
      created_at TIMESTAMP DEFAULT NOW()
  );
  ```

- **Example FastAPI Endpoint**:
  ```python
  from fastapi import FastAPI, Request, HTTPException

  app = FastAPI()

  @app.post("/github/webhook")
  async def handle_github_webhook(request: Request):
      payload = await request.json()
      event = request.headers.get("X-GitHub-Event")
      if event != "pull_request":
          raise HTTPException(status_code=400, detail="Unsupported event")
      # Process PR data and store in PostgreSQL
      return {"status": "success"}
  ```

---

### **User Story 2: AI-Powered PR Analysis**
**As a developer, I want codemop to analyze my PR for bugs and suggest fixes, so I can improve code quality.**

#### **Acceptance Criteria**
1. **AI Integration**:
   - Call Mistral/Claude API with PR diff (e.g., `curl https://api.mistral.ai/v1/analysis`).
   - Parse the response for suggested fixes (e.g., line number, description, fix).

2. **Store Suggestions**:
   - Store suggestions in PostgreSQL with a reference to the PR.
   - Example suggestion:
     ```json
     {
       "pr_id": 123,
       "line_number": 42,
       "description": "Add null check for `items`",
       "fix": "if items == nil { return 0 }",
       "confidence": 0.95
     }
     ```

3. **Error Handling**:
   - Retry failed AI API calls (max 3 retries).
   - Log errors (e.g., "AI analysis failed for PR #123").

#### **Technical Details**
- **AI API Input**:
  Send the PR diff to Mistral/Claude:
  ```python
  import httpx

  async def analyze_pr(diff: str) -> list:
      async with httpx.AsyncClient() as client:
          response = await client.post(
              "https://api.mistral.ai/v1/analysis",
              json={"diff": diff},
              headers={"Authorization": "Bearer YOUR_API_KEY"}
          )
          return response.json()["suggestions"]
  ```

- **Database Schema for Suggestions**:
  ```sql
  CREATE TABLE suggestions (
      id SERIAL PRIMARY KEY,
      pr_id INTEGER REFERENCES prs(id),
      line_number INTEGER NOT NULL,
      description TEXT NOT NULL,
      fix TEXT NOT NULL,
      confidence FLOAT NOT NULL
  );
  ```

---

### **User Story 3: Basic API for Suggestions**
**As a developer, I want to fetch PR suggestions via an API, so I can build a frontend/extension later.**

#### **Acceptance Criteria**
1. **API Endpoint**:
   - `GET /pr/{id}/suggestions` returns all suggestions for a PR.
   - Example response:
     ```json
     [
       {
         "id": 1,
         "line_number": 42,
         "description": "Add null check for `items`",
         "fix": "if items == nil { return 0 }"
       }
     ]
     ```

2. **Authentication**:
   - Use API keys (or JWT) to secure the endpoint.
   - Example header: `Authorization: Bearer YOUR_API_KEY`.

#### **Technical Details**
- **FastAPI Endpoint**:
  ```python
  from fastapi import HTTPException

  @app.get("/pr/{pr_id}/suggestions")
  async def get_suggestions(pr_id: int):
      suggestions = await db.query("SELECT * FROM suggestions WHERE pr_id = ?", pr_id)
      if not suggestions:
          raise HTTPException(status_code=404, detail="PR not found")
      return suggestions
  ```

---

### **Deliverables for Epic 1**
1. **Backend Deployed**:
   - Deploy to Vercel/AWS with a public URL (e.g., `https://codemop-backend.com`).
   - GitHub webhook configured and working.

2. **AI Suggestions Working**:
   - Test PR triggers AI analysis, and suggestions are stored in PostgreSQL.

3. **API Functional**:
   - `GET /pr/{id}/suggestions` returns valid data for a test PR.

---

### **Example Workflow**
1. Developer opens a PR in `gregs-org/test-repo`.
2. GitHub sends a webhook to codemop backend.
3. Backend:
   - Validates the event.
   - Stores PR metadata in PostgreSQL.
   - Calls Mistral/Claude API with the PR diff.
   - Stores suggestions in PostgreSQL.
4. Developer queries `GET /pr/123/suggestions` and sees AI suggestions.

---

### **Next Steps**
1. **Set Up the Backend**:
   - Initialize FastAPI project.
   - Configure PostgreSQL and Redis.
   - Write the webhook and API endpoints.

2. **Test with a Real PR**:
   - Use a test repo (e.g., `gregs-org/codemop-test`) to simulate PRs.

Would you like me to provide a **step-by-step guide** for any of these tasks (e.g., GitHub webhook setup, FastAPI deployment)? Or would you prefer to dive into the VS Code extension (Epic 2) next?