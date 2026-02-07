"""
Original webhook tests refactored to use the new test framework.
These tests provide additional coverage and edge case testing.
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os
import hmac
import hashlib
import json

# Add the src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from app.main import app

# Create a fresh client for each test to avoid state issues
def create_test_client():
    """Create a fresh test client with proper isolation."""
    return TestClient(app)

def test_health_check():
    """Test health check endpoint (original test)."""
    client = create_test_client()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_webhook_without_signature():
    """Test webhook without signature (original test)."""
    client = create_test_client()
    
    payload = {
        "action": "opened",
        "number": 123,
        "pull_request": {
            "title": "Test PR",
            "user": {"login": "testuser"},
            "head": {"ref": "test-branch"}
        },
        "repository": {
            "full_name": "testuser/testrepo"
        }
    }

    response = client.post(
        "/api/v1/github/webhook",
        data=json.dumps(payload),
        headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"}
    )

    # Should fail without signature
    assert response.status_code == 401

def test_webhook_with_valid_signature():
    """Test webhook with valid signature (original test)."""
    client = create_test_client()
    
    payload = {
        "action": "opened",
        "number": 123,
        "pull_request": {
            "title": "Test PR",
            "user": {"login": "testuser"},
            "head": {"ref": "test-branch"}
        },
        "repository": {
            "full_name": "testuser/testrepo"
        }
    }

    body = json.dumps(payload)
    # Use the actual secret from .env file
    from app.config import settings
    secret = settings.GITHUB_WEBHOOK_SECRET.encode()
    signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()

    response = client.post(
        "/api/v1/github/webhook",
        data=body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["pr_number"] == 123
    assert data["action"] == "opened"

def test_webhook_non_pr_event():
    """Test webhook with non-PR event (original test)."""
    client = create_test_client()
    
    payload = {"ref": "refs/heads/main"}

    response = client.post(
        "/api/v1/github/webhook",
        data=json.dumps(payload),
        headers={"X-GitHub-Event": "push", "Content-Type": "application/json"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert data["reason"] == "not a pull_request event"