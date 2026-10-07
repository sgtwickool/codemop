# codemop - AI-Augmented Code Review & Debugging Hub

## 🚀 CI/CD Status

[![CI Status](https://github.com/sgtwickool/codemop/actions/workflows/ci.yml/badge.svg)](https://github.com/sgtwickool/codemop/actions/workflows/ci.yml)
[![Docker Build](https://github.com/sgtwickool/codemop/actions/workflows/docker.yml/badge.svg)](https://github.com/sgtwickool/codemop/actions/workflows/docker.yml)
[![Security Scan](https://github.com/sgtwickool/codemop/actions/workflows/security.yml/badge.svg)](https://github.com/sgtwickool/codemop/actions/workflows/security.yml)
[![Codecov](https://codecov.io/gh/sgtwickool/codemop/branch/master/graph/badge.svg)](https://codecov.io/gh/sgtwickool/codemop)

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
fixed test settings (see `backend/tests/conftest.py`).

**Run all tests:**
```bash
cd backend
pytest
```

**Run specific tests:**
```bash
cd backend
pytest tests/integration/test_webhook_integration.py -k health
```

**Try a service function interactively:**
```bash
cd backend
PYTHONPATH=src python -c "
from app.services.github import extract_pr_data
payload = {'action': 'opened', 'number': 123, 'pull_request': {'title': 'Test'}, 'repository': {'full_name': 'test/repo'}}
print(extract_pr_data(payload))
"
```

### Database migrations
The server applies any pending migrations when it starts (and `setup_dev.sh` runs them too),
so there's nothing to run by hand. After changing a model in `backend/src/app/models/`,
generate a migration, review it, and commit it:
```bash
cd backend
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
3. Activate and install: `source venv/bin/activate && pip install -r backend/requirements-dev.txt`

### API Endpoints
- `POST /api/v1/github/webhook` - GitHub webhook endpoint (versioned)
- `GET /api/v1/health` - Health check endpoint (versioned)
- `GET /api/v1/repos/{owner}/{repo}/pulls/{number}/suggestions` - Get suggestions for a PR by repo and PR number (needs `Authorization: Bearer <API_KEY>`)
- `GET /api/v1/pr/{pr_id}/suggestions` - The same, by CodeMop's database ID (the webhook response's `database_id`)

**Note**: All endpoints are versioned under the `/api/v1/` prefix. Interactive API docs are at `/api/v1/docs`.

### Project Structure
```
codemop/
├── backend/                  # FastAPI backend
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
- FastAPI backend with GitHub webhook endpoint
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
See [ROADMAP.md](ROADMAP.md).

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
pip install -r backend/requirements-dev.txt

# Run tests (coverage is reported by default)
cd backend
pytest

# Run security scanning
pip-audit -r requirements.txt
bandit -c .bandit -r src/
```

#### Building Docker Images Locally
```bash
# Build production image
docker build -f backend/Dockerfile.prod -t codemop:latest backend/

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
