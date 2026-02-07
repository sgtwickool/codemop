import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add the src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from app.main import app
import hmac
import hashlib
import json

client = TestClient(app)

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_webhook_without_signature():
    # Set webhook secret to match the one in .env
    os.environ["GITHUB_WEBHOOK_SECRET"] = "50545ccdae7a6aa99792b6cb52ccfc89a9f9b7c0e1d634194817a1642405b7d0"

    # Reload app to pick up new env var
    from importlib import reload
    import app.main
    reload(app.main)

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
    os.environ["GITHUB_WEBHOOK_SECRET"] = "50545ccdae7a6aa99792b6cb52ccfc89a9f9b7c0e1d634194817a1642405b7d0"

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
    secret = "50545ccdae7a6aa99792b6cb52ccfc89a9f9b7c0e1d634194817a1642405b7d0".encode()
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
    # Test without webhook secret first (should be allowed for non-PR events)
    if "GITHUB_WEBHOOK_SECRET" in os.environ:
        del os.environ["GITHUB_WEBHOOK_SECRET"]
    
    # Reload app to pick up removed env var
    from importlib import reload
    import app.main
    reload(app.main)

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