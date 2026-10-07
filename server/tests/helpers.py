"""
Builders and constants shared by the tests. (Fixtures live in conftest.py.)
"""
import hashlib
import hmac
from typing import Any, Awaitable, Callable, Dict, List, Optional

from codemop.providers.base import Usage
from codemop.review.schema import ModelReview, ModelSuggestion

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


# A diff that adds app.py with 30 lines, so suggestions on lines 1-30 of app.py can be placed
SAMPLE_DIFF = (
    "diff --git a/app.py b/app.py\nnew file mode 100644\n--- /dev/null\n+++ b/app.py\n"
    "@@ -0,0 +1,30 @@\n" + "".join(f"+line {i}\n" for i in range(1, 31))
)


def suggestion(title: str, line: int = 10, **overrides) -> Dict[str, Any]:
    """A suggestion as a model returns it (the fields of codemop's ModelSuggestion)."""
    data = {
        "file_path": "app.py",
        "line": line,
        "severity": "bug",
        "title": title,
        "explanation": f"Why {title.lower()} matters",
        "suggested_code": "fixed()",
        "confidence": 0.9,
    }
    return {**data, **overrides}


class FakeReviewModel:
    """A codemop ReviewModel whose answer comes from `respond(diff_text)`, a list of suggestion dicts."""
    name = "fake/model"
    chunk_tokens = 40_000

    def cost(self, usage):
        return None

    def __init__(self, respond: Callable[[str], Awaitable[List[Dict[str, Any]]]]):
        self.respond = respond

    async def review(self, instructions: str, diff_text: str):
        suggestions = await self.respond(diff_text)
        return (
            ModelReview(suggestions=[ModelSuggestion(**s) for s in suggestions]),
            Usage(input_tokens=100, output_tokens=10),
        )
