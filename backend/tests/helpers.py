"""
Builders and constants shared by the tests. (Fixtures live in conftest.py.)
"""
import hashlib
import hmac
from typing import Any, Dict, Optional

TEST_WEBHOOK_SECRET = "test_secret"
TEST_API_KEY = "test_api_key"
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_KEY}"}


def sign_body(body) -> str:
    """GitHub's X-Hub-Signature-256 value for a raw request body."""
    if isinstance(body, str):
        body = body.encode()
    return "sha256=" + hmac.new(TEST_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def pr_event(
    action: str = "opened",
    number: int = 123,
    repo: str = "testuser/testrepo",
    title: str = "Test PR",
    sha: Optional[str] = "a" * 40,
    state: str = "open",
    merged: bool = False,
    draft: bool = False,
) -> Dict[str, Any]:
    """A pull_request webhook payload."""
    return {
        "action": action,
        "number": number,
        "pull_request": {
            "title": title,
            "user": {"login": "testuser"},
            "head": {"ref": "test-branch", "sha": sha},
            "state": state,
            "merged": merged,
            "draft": draft,
            "html_url": f"https://github.com/{repo}/pull/{number}",
        },
        "repository": {"name": repo.split("/")[1], "full_name": repo},
    }


def pr_data(**overrides) -> Dict[str, Any]:
    """The fields of a stored PR, as passed to pr_service.create_pr."""
    data = {
        "number": 123,
        "repo_name": "testrepo",
        "repo_full_name": "testuser/testrepo",
        "branch": "test-branch",
        "author": "testuser",
        "title": "Test PR",
        "status": "open",
        "github_url": "https://github.com/testuser/testrepo/pull/123",
    }
    return {**data, **overrides}
