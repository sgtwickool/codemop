#!/bin/bash
# Run development server
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -d venv ]; then
    source venv/bin/activate
fi

echo "Starting codemop development server..."
cd server
uvicorn app.main:app --app-dir src --reload --host 0.0.0.0 --port 8000
