# codemop - AI-Augmented Code Review & Debugging Hub

## Development Setup

### Prerequisites
- Python 3.9+
- PostgreSQL 13+
- Docker (optional)
- ngrok (for webhook testing)

### Installation
1. Clone the repository
2. Copy `.env.example` to `.env` and configure
3. Run `./scripts/setup_dev.sh`
4. Start the development server: `./scripts/run_dev.sh`

### GitHub Webhook Setup
1. Install ngrok: `brew install ngrok` (or download from ngrok.com)
2. Start ngrok: `ngrok http 8000`
3. Configure GitHub webhook with the ngrok URL
4. Set the webhook secret in your `.env` file

### Testing
Run tests with:
```bash
cd backend
pytest tests/
```

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