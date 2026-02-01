#!/bin/bash

# Run development server
echo "Starting codemop development server..."

# Start backend
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
