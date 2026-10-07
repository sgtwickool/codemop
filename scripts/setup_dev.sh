#!/bin/bash
# Set up a local development environment for codemop
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Setting up codemop development environment..."

# Create virtual environment
if [ ! -d venv ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# Install the codemop package (editable) and the server's dev/test dependencies
pip install --upgrade pip
pip install -e . -r backend/requirements-dev.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example - fill in your secrets before running the server"
fi

# Set up database
echo "Setting up database..."
# If your user can't create databases, run: sudo -u postgres createdb codemop
createdb codemop 2>/dev/null || echo "Database already exists (or run: sudo -u postgres createdb codemop)"

# Initialize database tables
(cd backend && PYTHONPATH=src python -c "from app.db.session import init_db; init_db()")

echo "Development environment setup complete!"
echo "Run the tests with: cd backend && pytest"
echo "Start the server with: ./scripts/run_dev.sh"
