# CodeMop

AI code review for pull requests, with the model of your choice.

## 🚀 CI/CD Status

[![CI Status](https://github.com/sgtwickool/codemop/actions/workflows/ci.yml/badge.svg)](https://github.com/sgtwickool/codemop/actions/workflows/ci.yml)
[![Docker Build](https://github.com/sgtwickool/codemop/actions/workflows/docker.yml/badge.svg)](https://github.com/sgtwickool/codemop/actions/workflows/docker.yml)
[![Security Scan](https://github.com/sgtwickool/codemop/actions/workflows/security.yml/badge.svg)](https://github.com/sgtwickool/codemop/actions/workflows/security.yml)
[![Codecov](https://codecov.io/gh/sgtwickool/codemop/branch/master/graph/badge.svg)](https://codecov.io/gh/sgtwickool/codemop)

## Quick start

```bash
pipx install codemop                  # or: uv tool install codemop
export ANTHROPIC_API_KEY=sk-ant-...   # or use another provider (see "Choosing a model")

codemop review owner/repo#123         # a pull request (GITHUB_TOKEN or `gh auth login` for private repos)
codemop review owner/repo#123 --post  # ...and post the review on it
git diff main | codemop review -      # your local changes
```

It prints each suggestion with the file and line, the reason, and a fix where it has one,
then the tokens used and an estimated cost (about two cents a review with the default
model). `--json` prints the report for scripts.

`--post` posts it on the pull request: a comment on each issue, with a one-click "Commit
suggestion" when there's a fix, and one summary comment in the PR's conversation that later
reviews update in place. It never approves or blocks the PR, and a commit it has already
reviewed isn't reviewed (or paid for) again. Posting needs a token that can write to pull
requests.

## GitHub Action

Reviews every pull request, and commits the fixes you tick. Add your provider's API key as a
repository secret (Settings → Secrets and variables → Actions, e.g. `ANTHROPIC_API_KEY`),
then add `.github/workflows/codemop.yml`:

```yaml
name: CodeMop
on:
  pull_request_target:
    types: [opened, synchronize, reopened, ready_for_review]
  issue_comment:
    types: [edited]  # someone ticked fixes in CodeMop's summary

permissions:
  contents: write  # to commit ticked fixes (read is enough without them)
  pull-requests: write

concurrency:  # a new push replaces a review still running; fixes wait their turn
  group: codemop-${{ github.event_name == 'issue_comment' && 'fixes' || 'review' }}-${{ github.event.pull_request.number || github.event.issue.number }}
  cancel-in-progress: ${{ github.event_name != 'issue_comment' }}

jobs:
  codemop:
    # On comment edits, only CodeMop's own summary on a pull request
    if: github.event_name != 'issue_comment' || (github.event.issue.pull_request && contains(github.event.comment.body, 'codemop-summary'))
    runs-on: ubuntu-latest
    steps:
      - uses: sgtwickool/codemop@v1
        with:
          api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          # provider: mistral        # or openai, openrouter, openai-compatible
          # model: codestral-latest
          # max-changed-lines: 3000  # don't review (or pay for) PRs bigger than this
```

The summary comment lists what CodeMop found, with a checkbox for each issue that has a
fix. Tick the ones you want and CodeMop commits them to the PR's branch as one commit:
only for people with write access to the repository, and only where the code they replace
hasn't changed since the review (the summary says which were applied, and why any weren't).
GitHub doesn't run other workflows for a commit made with the workflow's own token, so CI
doesn't run on a fix commit: its checks show as failed to start ("a workflow file issue").
To have CI run on fix commits, pass a personal access token (contents and pull requests:
write) as `github-token`. Pull requests from forks get no checkboxes, since their branches can't be
committed to; their comments still have one-click suggestions. `checklist: false` turns
the checkboxes off.

**Pull requests from forks are reviewed too, safely.** `pull_request_target` gives the
workflow your secret even for a fork's PR, which is only safe because CodeMop never checks
out or runs the PR's code: it reads the diff through the API, the model has no tools, and
the review settings come from your default branch's `.codemop.yml`, so a PR can't change
how it's reviewed. The worst a malicious PR can do is get a bad comment posted. Don't add
`actions/checkout` of the PR to this job. (With `on: pull_request` instead, forks' PRs
aren't reviewed, because GitHub doesn't give their workflows your secrets.)

Drafts are skipped until they're ready for review (`review-drafts: true` to review them),
and the job fails only when the review couldn't be done (a rejected key, say). The other
inputs: `base-url`, `effort` (Claude: `low` is cheaper), `max-comments` and `github-token`.

The rest of this README covers configuring reviews, choosing a model, and running the
webhook server.

## 🏗️ Development Setup

### Prerequisites
- Python 3.12+ (Python 3.14 recommended)
- PostgreSQL 13+ (or any recent version)
- Docker (optional, for containerized development)
- ngrok (for webhook testing) - [Download ngrok](https://ngrok.com/download)

#### Fedora/Linux Installation Notes
```bash
# Install Python and PostgreSQL on Fedora
sudo dnf install python3 python3-pip postgresql-server postgresql-contrib

# Initialize and start PostgreSQL
sudo postgresql-setup --initdb
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Install ngrok (download from ngrok.com and follow their instructions)
# Or use their official Fedora package if available
```

### Installation
1. Clone the repository
2. Copy `.env.example` to `.env` and configure your settings:
   ```bash
   cp .env.example .env
   ```
   `GITHUB_WEBHOOK_SECRET` and `API_KEY` are required: the server refuses to start without
   them unless `APP_ENV=development` (which `.env.example` sets). `APP_ENV` defaults to
   `production` when unset.
3. Install dependencies and set up the database (creates `venv/` and, if missing, `.env`):
   ```bash
   ./scripts/setup_dev.sh
   ```
4. Start the development server:
   ```bash
   ./scripts/run_dev.sh
   ```

### GitHub Webhook Setup
1. **Install ngrok**: Download and install ngrok for your platform from [ngrok.com/download](https://ngrok.com/download)
2. **Start ngrok tunnel**:
   ```bash
   ngrok http 8000
   ```
3. **Configure GitHub Webhook**:
   - Go to your GitHub repository → Settings → Webhooks
   - Add webhook with the ngrok URL (e.g., `https://abc123.ngrok.io/api/v1/github/webhook`)
   - Set content type to `application/json`
   - Add your webhook secret (same as in `.env` file)
   - Select "Let me select individual events" and check "Pull requests"
4. **Private repositories**: set `GITHUB_TOKEN` in `.env` so CodeMop can fetch PR diffs through the GitHub API. Create a [fine-grained token](https://github.com/settings/personal-access-tokens/new) limited to the repos you want reviewed, with read-only **Pull requests** and **Contents** permissions. Public repos work without one, but a token raises the API rate limit from 60 to 5,000 requests an hour.
5. **Test the webhook**: GitHub sends a `ping` when the webhook is created; its delivery log should show `"status": "pong"`. Then open a test pull request and check that delivery too

### Testing

The tests need no database, network or `.env`: they use a temporary SQLite database and
fixed test settings (see `server/tests/conftest.py`).

**Run all tests:**
```bash
cd server
pytest
```

**Run specific tests:**
```bash
cd server
pytest tests/integration/test_webhook_integration.py -k health
```

**Try a service function interactively:**
```bash
cd server
PYTHONPATH=src python -c "
from app.services.github import extract_pr_data
payload = {'action': 'opened', 'number': 123, 'pull_request': {'title': 'Test'}, 'repository': {'full_name': 'test/repo'}}
print(extract_pr_data(payload))
"
```

### Configuring reviews
A repository can include a `.codemop.yml` to say how its pull requests are reviewed:
```yaml
ignore:              # paths not to review, added to the defaults (lock files, minified files...)
  - "docs/*"
  - "*.snap"
min_confidence: 0.6  # drop suggestions the model is less sure of (default: 0.5)
chunk_tokens: 20000  # largest piece of diff sent in one request (default: the model's own)
max_comments: 5      # most inline comments in a posted review; the rest go in its summary (default: 10)
```
CodeMop reads it from the repository's **default branch**, so a pull request can't change how it's
reviewed (for `codemop review -`, from the current directory; `--config PATH` uses another file).
Command-line flags override it.

It can't choose the provider or model, or where requests go: whoever runs CodeMop decides that, with
`--provider` / `--model` / `--base-url` or `CODEMOP_PROVIDER` / `CODEMOP_MODEL` / `CODEMOP_BASE_URL`
(and the server's `AI_*` settings). Otherwise reviewing someone else's pull request could send your API
key to their server.

Each review ends with the tokens used and, where the model's list price is known, an estimated cost.

### Choosing a model
The default is Claude Opus 5.5 (`claude-opus-5-5`) at high effort, chosen by the
[review eval](https://github.com/sgtwickool/codemop/blob/master/evals/review/README.md): it found the most known issues, with almost no false alarms,
for about two cents a review. `--effort` (or `CODEMOP_EFFORT`) sets Claude's effort level. For less
cost, `--model claude-sonnet-5-5 --effort low` was as good on simple changes and missed a little more
on complex ones. Claude Haiku 4.5 isn't recommended: half its comments were wrong.

### Reviewing with a local model (Ollama)
The `codemop` command can review with a model running on your own machine: no API key, no cost per
review, and the code never leaves your computer. It's slower, and small models review less well.
```bash
ollama pull qwen2.5-coder:7b
codemop review owner/repo#123 --provider ollama --model qwen2.5-coder:7b
```
Ollama runs models with a 4,096-token context window by default, which has to hold the instructions,
a chunk of the diff and the review, so raise it. On Linux, where Ollama runs as a systemd service:
```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '[Service]\nEnvironment="OLLAMA_CONTEXT_LENGTH=16384"\n' | sudo tee /etc/systemd/system/ollama.service.d/context.conf
sudo systemctl daemon-reload && sudo systemctl restart ollama
```
CodeMop sends Ollama 8,000-token chunks and checks the token count Ollama reports back: if part of the
input was dropped, it stops with an error instead of reviewing a fragment.

### Database migrations
The server applies any pending migrations when it starts (and `setup_dev.sh` runs them too),
so there's nothing to run by hand. After changing a model in `server/src/app/models/`,
generate a migration, review it, and commit it:
```bash
cd server
alembic revision --autogenerate -m "describe the change"   # creates src/app/migrations/versions/<rev>_....py
alembic upgrade head                                       # apply it to the database in DATABASE_URL
```

### Troubleshooting

#### Database Connection Issues
If you get database connection errors:
1. Make sure PostgreSQL is running: `sudo systemctl status postgresql`
2. Try creating the database as postgres user: `sudo -u postgres createdb codemop`
3. Check your `.env` file has the correct DATABASE_URL

#### Port Already in Use
If port 8000 is in use:
1. Find the process: `lsof -i :8000`
2. Kill it: `kill -9 <PID>` or use a different port

#### Python Virtual Environment Issues
If you have virtual environment issues:
1. Remove existing venv: `rm -rf venv`
2. Recreate it: `python -m venv venv`
3. Activate and install: `source venv/bin/activate && pip install -r server/requirements-dev.txt`

### API Endpoints
- `POST /api/v1/github/webhook` - GitHub webhook endpoint (versioned)
- `GET /api/v1/health` - Health check endpoint (versioned)
- `GET /api/v1/repos/{owner}/{repo}/pulls/{number}/suggestions` - Get suggestions for a PR by repo and PR number (needs `Authorization: Bearer <API_KEY>`)
- `GET /api/v1/pr/{pr_id}/suggestions` - The same, by CodeMop's database ID (the webhook response's `database_id`)

**Note**: All endpoints are versioned under the `/api/v1/` prefix. Interactive API docs are at `/api/v1/docs`.

### Project Structure
```
codemop/
├── server/                  # FastAPI server
│   ├── src/                 # Source code (modern structure)
│   │   ├── app/             # Main application package
│   │   │   ├── main.py      # FastAPI app setup
│   │   │   ├── config.py    # Configuration management
│   │   │   ├── api/         # Versioned API endpoints
│   │   │   │   └── v1/      # API version 1
│   │   │   │       ├── endpoints/ # Individual endpoints
│   │   │   │       └── api.py # API router
│   │   │   ├── core/        # Core utilities
│   │   │   ├── services/    # Business logic
│   │   │   ├── models/      # Database models
│   │   │   ├── db/          # Database layer
│   │   │   ├── utils/       # Utilities
│   │   │   └── migrations/  # Alembic database migrations
│   ├── tests/               # Test files
│   ├── requirements.txt     # Runtime dependencies (pinned)
│   ├── requirements-dev.txt # Test and security tooling
│   ├── Dockerfile           # Docker configuration
│   ├── pytest.ini           # Pytest configuration
│   └── .bandit              # Bandit security config
├── .github/                 # GitHub Actions workflows
│   └── workflows/           # CI/CD pipelines
│       ├── ci.yml           # Continuous Integration
│       ├── docker.yml       # Docker builds
│       ├── security.yml     # Security scanning
│       └── README.md        # Workflow documentation
├── ROADMAP.md                # Plan and decisions
├── docs/                     # Documentation
├── scripts/                  # Development scripts
├── .gitignore
├── .env.example
├── docker-compose.yml
└── README.md
```

## User Story 1: GitHub Webhook Integration

This implementation provides:
- FastAPI server with GitHub webhook endpoint
- Webhook signature validation for security
- PR data extraction and logging
- Database schema for PR storage
- Docker setup for local development
- Comprehensive testing framework

### Features Implemented
✅ GitHub webhook endpoint with signature validation
✅ PR event handling and data extraction
✅ Database models for PRs and suggestions
✅ Docker and docker-compose configuration
✅ Development scripts for easy setup
✅ Test suite with pytest

### Next Steps
See [ROADMAP.md](https://github.com/sgtwickool/codemop/blob/master/ROADMAP.md).

## 🚀 CI/CD Pipeline

CodeMop uses GitHub Actions for Continuous Integration and Deployment with the following workflows:

### Continuous Integration (CI)
- **Trigger**: Push to `master`/`develop`, Pull Requests
- **Features**:
  - Python 3.12, 3.13, 3.14 test matrix
  - Automated test execution with pytest
  - Code coverage reporting via Codecov

### Docker Build & Push
- **Trigger**: Push to `master`, version tags
- **Features**:
  - Multi-stage Docker builds
  - Automatic image tagging
  - GitHub Container Registry integration
  - Docker layer caching for faster builds

### Security Scanning
- **Trigger**: Push to `master`/`develop`, Pull Requests, Weekly schedule
- **Features**:
  - **pip-audit**: Dependency vulnerability scanning
  - **Bandit**: Python security linting using configuration file
  - **Trivy**: Container vulnerability scanning
  - Scheduled weekly scans

### Local Development with CI/CD

#### Running Tests Locally
```bash
# Install test and security tooling
pip install -r server/requirements-dev.txt

# Run tests (coverage is reported by default)
cd server
pytest

# Run security scanning
pip-audit -r requirements.txt
bandit -c .bandit -r src/
```

#### Building Docker Images Locally
```bash
# Build production image
docker build -f server/Dockerfile.prod -t codemop:latest server/

# Run the container
docker run -p 8000:8000 --env-file .env codemop:latest
```

### CI/CD Best Practices

1. **Small, Focused Commits**: Keep changes small for easier testing
2. **Test Locally First**: Run tests before pushing to CI
3. **Monitor Workflows**: Check GitHub Actions tab regularly
4. **Fix Failures Promptly**: Address CI failures immediately
5. **Use Feature Branches**: Create branches for new features
6. **Pull Request Workflow**: All changes go through PR review

### Troubleshooting CI/CD

#### Test Failures
- Check the specific test that failed
- Run tests locally to reproduce
- Fix the issue and push the correction

#### Docker Build Failures
- Verify `Dockerfile.prod` syntax
- Check for missing files in build context
- Ensure proper permissions

#### Security Scan Failures
- Review vulnerability reports
- Update vulnerable dependencies
- Add exceptions for false positives if necessary
