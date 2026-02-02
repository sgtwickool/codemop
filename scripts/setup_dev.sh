#!/bin/bash

# Set up development environment
echo "Setting up codemop development environment..."

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install backend dependencies
cd backend
pip install -r requirements.txt

# Set up database
echo "Setting up database..."

# Note: You may need to run createdb as the postgres user
# Option 1: Run as postgres user (recommended for most systems)
# sudo -u postgres createdb codemop || echo "Database already exists"

# Option 2: If your current user has postgres permissions
createdb codemop 2>/dev/null || echo "Database already exists (or run: sudo -u postgres createdb codemop)"

# Initialize database tables
python -c "from src.database import init_db; init_db()"

# Install pre-commit hooks
cd ..
pip install pre-commit
pre-commit install

echo "Development environment setup complete!"
