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
createdb codemop || echo "Database already exists"
python -c "from src.database import init_db; init_db()"

# Install pre-commit hooks
cd ..
pip install pre-commit
pre-commit install

echo "Development environment setup complete!"
