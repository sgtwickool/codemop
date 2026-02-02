import pytest
from fastapi.testclient import TestClient
from src.main import app
import os
import hmac
import hashlib
import json

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_webhook_without_signature():
    # Set webhook secret
    os.environ["GITHUB_WEBHOOK_SECRET"] = "test_secret"

    # Reload app to pick up new env var
    from importlib import reload
    import src.main
    reload(src.main)

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
        "/github/webhook",
        json=payload,
        headers={"X-GitHub-Event": "pull_request"}
    )

    # Should fail without signature
    assert response.status_code == 401

def test_webhook_with_valid_signature():
    os.environ["GITHUB_WEBHOOK_SECRET"] = "test_secret"

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
    secret = "test_secret".encode()
    signature = "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()

    response = client.post(
        "/github/webhook",
        json=payload,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": signature
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
    import src.main
    reload(src.main)

    payload = {"ref": "refs/heads/main"}

    response = client.post(
        "/github/webhook",
        json=payload,
        headers={"X-GitHub-Event": "push"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert data["reason"] == "not a pull_request event"