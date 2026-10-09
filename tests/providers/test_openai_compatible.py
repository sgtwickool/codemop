"""
The OpenAI-compatible adapter, against a fake API (httpx.MockTransport).
"""
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from codemop.providers.base import NoReview
from codemop.providers.openai_compatible import OpenAICompatibleModel

VALID = {"suggestions": [{
    "file_path": "app.py", "line": 3, "severity": "bug", "title": "Off by one",
    "explanation": "e", "suggested_code": None, "confidence": 0.9,
}]}


def completion(content, finish_reason="stop", refusal=None):
    return {
        "choices": [{"message": {"content": content, "refusal": refusal}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
    }


class FakeAPI:
    """Replies with each queued (status, body) in turn and records the requests"""
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, body = self.replies.pop(0)
        return httpx.Response(status, json=body) if isinstance(body, dict) else httpx.Response(status, text=body)


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr("codemop.providers.openai_compatible.asyncio.sleep", AsyncMock())


def model(api, **kwargs):
    kwargs.setdefault("provider", "mistral")
    kwargs.setdefault("api_key", "k")
    return OpenAICompatibleModel("codestral-latest", transport=httpx.MockTransport(api), **kwargs)


@pytest.mark.asyncio
async def test_returns_the_review_and_usage():
    api = FakeAPI((200, completion(json.dumps(VALID))))

    review, usage = await model(api).review("instructions", "### app.py (modified)")

    assert review.suggestions[0].title == "Off by one"
    assert (usage.input_tokens, usage.output_tokens) == (1000, 200)
    [request] = api.requests
    assert str(request.url) == "https://api.mistral.ai/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer k"
    body = json.loads(request.content)
    assert body["model"] == "codestral-latest"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["response_format"]["type"] == "json_schema"
    assert "suggestions" in body["response_format"]["json_schema"]["schema"]["properties"]


@pytest.mark.asyncio
async def test_presets_read_their_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "from-env")
    api = FakeAPI((200, completion(json.dumps(VALID))))

    await model(api, api_key=None).review("i", "d")

    assert api.requests[0].headers["Authorization"] == "Bearer from-env"


@pytest.mark.asyncio
async def test_local_models_need_no_key():
    api = FakeAPI((200, completion(json.dumps(VALID))))

    await model(api, provider="ollama", api_key=None).review("i", "d")

    assert str(api.requests[0].url) == "http://localhost:11434/v1/chat/completions"
    assert "Authorization" not in api.requests[0].headers


@pytest.mark.asyncio
async def test_an_invalid_answer_gets_one_repair_attempt():
    bad = {"suggestions": [{**VALID["suggestions"][0], "confidence": "very"}]}
    api = FakeAPI((200, completion(json.dumps(bad))), (200, completion(json.dumps(VALID))))

    review, usage = await model(api).review("i", "d")

    assert review.suggestions[0].confidence == 0.9
    assert usage.input_tokens == 2000  # both requests counted
    repair = json.loads(api.requests[1].content)["messages"]
    assert [m["role"] for m in repair] == ["system", "user", "assistant", "user"]
    assert "didn't match the required JSON schema" in repair[-1]["content"]


@pytest.mark.asyncio
async def test_gives_up_after_the_repair_attempt():
    api = FakeAPI((200, completion("not json")), (200, completion("still not json")))

    with pytest.raises(NoReview) as error:
        await model(api).review("i", "d")

    assert "doesn't match the schema, even after a retry" in error.value.reason
    assert error.value.usage.input_tokens == 2000


@pytest.mark.asyncio
@pytest.mark.parametrize("reply, expected, kind", [
    (completion("", refusal="I can't help with that"), "declined", "refused"),
    (completion("", finish_reason="content_filter"), "declined", "refused"),
    (completion('{"suggestions": [', finish_reason="length"), "cut off at 16000 output tokens", "cut_off"),
])
async def test_non_answers_say_why(reply, expected, kind):
    with pytest.raises(NoReview) as error:
        await model(FakeAPI((200, reply))).review("i", "d")

    assert expected in error.value.reason
    assert error.value.kind == kind
    assert not error.value.fatal


@pytest.mark.asyncio
@pytest.mark.parametrize("status, body, expected, fatal", [
    (401, "unauthorized", "mistral rejected the API key: check MISTRAL_API_KEY", True),
    (404, "no such model", "codestral-latest wasn't found at https://api.mistral.ai/v1", True),
    (400, "unknown field response_format", "doesn't support structured output", True),
    (400, "bad request", "returned an error (400): bad request", False),
])
async def test_errors_say_what_to_fix(status, body, expected, fatal):
    with pytest.raises(NoReview) as error:
        await model(FakeAPI((status, body))).review("i", "d")

    assert expected in error.value.reason
    assert error.value.fatal is fatal


@pytest.mark.asyncio
async def test_retryable_errors_are_retried():
    api = FakeAPI((503, "busy"), (429, "slow down"), (200, completion(json.dumps(VALID))))

    review, _ = await model(api).review("i", "d")

    assert len(api.requests) == 3
    assert review.suggestions


@pytest.mark.asyncio
async def test_rate_limit_after_retries():
    api = FakeAPI((429, "x"), (429, "x"), (429, "x"))

    with pytest.raises(NoReview) as error:
        await model(api).review("i", "d")

    assert "rate limit" in error.value.reason
    assert len(api.requests) == 3


def test_unknown_provider_needs_a_base_url():
    with pytest.raises(ValueError, match="give a base_url"):
        OpenAICompatibleModel("m", provider="somewhere-else")


@pytest.mark.asyncio
async def test_input_the_server_silently_dropped_is_never_passed_off_as_a_review():
    """Ollama reviews whatever fits its context window and says nothing (checked: ~13k tokens in, 2,050 read)"""
    big_diff = "+    value = compute(items[i])\n" * 2000  # ~62k characters
    reply = completion(json.dumps(VALID))
    reply["usage"] = {"prompt_tokens": 2050, "completion_tokens": 50}

    with pytest.raises(NoReview) as error:
        await model(FakeAPI((200, reply)), provider="ollama", api_key=None).review("instructions", big_diff)

    assert "only read 2,050 tokens" in error.value.reason
    assert "set OLLAMA_CONTEXT_LENGTH" in error.value.reason
    assert error.value.fatal


@pytest.mark.asyncio
async def test_normal_token_counts_pass_the_check():
    diff = "+    value = compute(items[i])\n" * 2000
    reply = completion(json.dumps(VALID))
    reply["usage"] = {"prompt_tokens": 16000, "completion_tokens": 50}  # ~4 characters a token

    review, _ = await model(FakeAPI((200, reply))).review("instructions", diff)

    assert review.suggestions


def test_ollama_gets_local_model_defaults():
    ollama = OpenAICompatibleModel("qwen2.5-coder:7b", provider="ollama")
    mistral = OpenAICompatibleModel("codestral-latest", provider="mistral")

    assert (ollama.chunk_tokens, ollama.max_output_tokens) == (8000, 4096)
    assert (mistral.chunk_tokens, mistral.max_output_tokens) == (40000, 16000)
    assert OpenAICompatibleModel("m", provider="ollama", chunk_tokens=3000).chunk_tokens == 3000
