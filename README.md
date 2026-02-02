# codemop - AI-Augmented Code Review & Debugging Hub

## Development Setup

### Prerequisites
- Python 3.9+ (Python 3.13 recommended)
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
3. Install dependencies and set up the database:
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
   - Add webhook with the ngrok URL (e.g., `https://abc123.ngrok.io/github/webhook`)
   - Set content type to `application/json`
   - Add your webhook secret (same as in `.env` file)
   - Select "Let me select individual events" and check "Pull requests"
4. **Test the webhook**: Create a test pull request and verify the webhook delivery in GitHub

### Testing
Run tests with:
```bash
cd backend
pytest tests/
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
3. Activate and install: `source venv/bin/activate && pip install -r backend/requirements.txt`

### API Endpoints
- `POST /github/webhook` - GitHub webhook endpoint
- `GET /health` - Health check endpoint

### Project Structure
```
codemop/
├── backend/                  # FastAPI backend
│   ├── src/                 # Source code
│   │   ├── main.py          # FastAPI application
│   │   └── database.py      # Database models
│   ├── tests/               # Test files
│   ├── requirements.txt     # Python dependencies
│   └── Dockerfile           # Docker configuration
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
1. Set up PostgreSQL database
2. Configure GitHub webhook
3. Implement AI analysis integration
4. Add suggestion storage functionality