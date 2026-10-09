"""
Unit tests for GitHub service functions: webhook signatures and pull_request payloads.
"""
import json

import pytest
from fastapi import HTTPException

from app.services.github import parse_pull_request_event, validate_github_webhook_signature
from tests.helpers import sign_body


def parse(payload, content_type="application/json"):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return parse_pull_request_event(content_type, body.encode())


class TestGitHubService:
    """Test GitHub service functions."""

    @pytest.mark.asyncio
    async def test_validate_github_webhook_signature_valid(self):
        body = json.dumps({"action": "opened", "number": 123}).encode()
        
        await validate_github_webhook_signature(body, sign_body(body))  # doesn't raise
    
    @pytest.mark.asyncio
    async def test_validate_github_webhook_signature_invalid(self):
        body = json.dumps({"action": "opened", "number": 123}).encode()
        
        with pytest.raises(HTTPException, match="Invalid signature"):
            await validate_github_webhook_signature(body, "invalid_signature")
    
    @pytest.mark.asyncio
    async def test_validate_github_webhook_signature_missing(self):
        body = json.dumps({"action": "opened", "number": 123}).encode()
        
        with pytest.raises(HTTPException, match="Missing signature"):
            await validate_github_webhook_signature(body, None)


class TestPullRequestEvent:
    """Parsing and validating pull_request payloads."""

    def test_pr_fields(self, github_webhook_payload):
        fields = parse(github_webhook_payload).pr_fields()

        assert fields == {
            "number": 123,
            "repo_name": "testrepo",
            "repo_full_name": "testuser/testrepo",
            "branch": "test-branch",
            "author": "testuser",
            "title": "Test PR",
            "status": "open",  # the PR state, not the webhook action
            "github_url": "https://github.com/testuser/testrepo/pull/123",
            "head_sha": "a" * 40,
        }

    @pytest.mark.parametrize("state, merged, expected", [
        ("open", False, "open"),
        ("closed", False, "closed"),
        ("closed", True, "merged"),
    ])
    def test_state(self, github_webhook_payload, state, merged, expected):
        github_webhook_payload["pull_request"].update(state=state, merged=merged)

        assert parse(github_webhook_payload).state == expected

    def test_unknown_fields_are_ignored(self, github_webhook_payload):
        github_webhook_payload["installation"] = {"id": 1}
        github_webhook_payload["pull_request"]["labels"] = [{"name": "bug"}]

        assert parse(github_webhook_payload).number == 123

    def test_missing_fields_are_named(self):
        with pytest.raises(HTTPException) as error:
            parse({"action": "opened", "number": 456, "pull_request": {}, "repository": {}})

        assert error.value.status_code == 422
        assert "missing required fields" in error.value.detail
        assert "pull_request.title" in error.value.detail
        assert "repository.full_name" in error.value.detail

    def test_wrong_types_are_rejected(self, github_webhook_payload):
        """A signed but malformed payload is a 422, not a database error."""
        github_webhook_payload["number"] = "abc"

        with pytest.raises(HTTPException) as error:
            parse(github_webhook_payload)

        assert error.value.status_code == 422
        assert "(number)" in error.value.detail

    @pytest.mark.parametrize("body", ["{not json", "[]", "true", ""])
    def test_bodies_that_arent_a_json_object_are_rejected(self, body):
        with pytest.raises(HTTPException) as error:
            parse(body)

        assert error.value.status_code == 422

    def test_non_json_content_type_is_415(self, github_webhook_payload):
        with pytest.raises(HTTPException) as error:
            parse(github_webhook_payload, content_type="application/x-www-form-urlencoded")

        assert error.value.status_code == 415
