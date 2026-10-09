"""
The Claude adapter, with a fake SDK client: no network, no API key.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import anthropic
import httpx2
import pytest

from codemop.providers.anthropic import AnthropicModel
from codemop.providers.base import NoReview
from codemop.review.schema import ModelReview, ModelSuggestion

REVIEW = ModelReview(suggestions=[ModelSuggestion(
    file_path="app.py", line=3, severity="bug", title="Off by one",
    explanation="range() stops one early", suggested_code="for i in range(n + 1):", confidence=0.9,
)])


def response(stop_reason="end_turn", parsed=REVIEW, category=None, model="claude-opus-5-5"):
    return SimpleNamespace(
        model=model,
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category=category) if category else None,
        parsed_output=parsed,
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300,
                              cache_read_input_tokens=None, cache_creation_input_tokens=0),
    )


def fake_client(result):
    """An AsyncAnthropic stand-in whose parse() calls return (or raise) `result`"""
    parse = AsyncMock(side_effect=result) if isinstance(result, Exception) else AsyncMock(return_value=result)
    return SimpleNamespace(
        messages=SimpleNamespace(parse=parse),
        beta=SimpleNamespace(messages=SimpleNamespace(parse=parse)),
    ), parse


def status_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("error", response=httpx2.Response(status, request=request), body=None)


@pytest.mark.asyncio
async def test_returns_the_review_and_usage():
    client, parse = fake_client(response())
    model = AnthropicModel(client=client)

    review, usage = await model.review("instructions", "### app.py (modified)")

    assert review == REVIEW
    assert (usage.input_tokens, usage.output_tokens, usage.cache_read_tokens) == (1200, 300, 0)
    request = parse.call_args.kwargs
    assert request["model"] == "claude-opus-5-5"
    assert request["system"] == "instructions"
    assert request["messages"] == [{"role": "user", "content": "### app.py (modified)"}]
    assert request["output_format"] is ModelReview
    assert request["output_config"] == {"effort": "high"}


@pytest.mark.asyncio
async def test_current_models_use_default_refusal_fallbacks():
    client, _ = fake_client(response())

    await AnthropicModel("claude-opus-5-5", client=client).review("i", "d")

    request = client.beta.messages.parse.call_args.kwargs
    assert request["betas"] == ["server-side-fallback-2026-07-01"]
    assert request["fallbacks"] == "default"


@pytest.mark.asyncio
async def test_older_models_get_neither_fallbacks_nor_effort():
    client, parse = fake_client(response())

    await AnthropicModel("claude-haiku-4-5", client=client).review("i", "d")

    request = parse.call_args.kwargs
    assert "fallbacks" not in request and "betas" not in request
    assert "output_config" not in request


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason, category, expected, kind", [
    ("refusal", "cyber", "declined to review this part of the diff (cyber)", "refused"),
    ("refusal", None, "declined to review this part of the diff", "refused"),
    ("max_tokens", None, "cut off at 16000 output tokens", "cut_off"),
])
async def test_non_answers_say_why(stop_reason, category, expected, kind):
    client, _ = fake_client(response(stop_reason, category=category))

    with pytest.raises(NoReview) as error:
        await AnthropicModel(client=client).review("i", "d")

    assert expected in error.value.reason
    assert error.value.kind == kind
    assert not error.value.fatal
    assert error.value.usage.input_tokens == 1200  # the tokens were still used


@pytest.mark.asyncio
async def test_no_credentials_at_all_is_a_clear_message():
    """The SDK raises TypeError (before sending anything) when it finds no credentials"""
    client, _ = fake_client(TypeError('"Could not resolve authentication method. Expected one of api_key..."'))

    with pytest.raises(NoReview) as raised:
        await AnthropicModel(client=client).review("i", "d")

    assert raised.value.reason == "No Anthropic API key found: set ANTHROPIC_API_KEY"
    assert raised.value.fatal


@pytest.mark.asyncio
async def test_other_type_errors_arent_hidden():
    client, _ = fake_client(TypeError("a bug"))

    with pytest.raises(TypeError, match="a bug"):
        await AnthropicModel(client=client).review("i", "d")


@pytest.mark.asyncio
@pytest.mark.parametrize("error, expected, fatal", [
    (status_error(anthropic.AuthenticationError, 401), "check ANTHROPIC_API_KEY", True),
    (status_error(anthropic.PermissionDeniedError, 403), "isn't allowed to use claude-opus-5-5", True),
    (status_error(anthropic.NotFoundError, 404), "claude-opus-5-5 wasn't found", True),
    (status_error(anthropic.RateLimitError, 429), "rate limit", False),
    (status_error(anthropic.InternalServerError, 500), "error (500)", False),
    (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")), "connect", False),
])
async def test_api_errors_say_what_to_fix(error, expected, fatal):
    client, _ = fake_client(error)

    with pytest.raises(NoReview) as raised:
        await AnthropicModel(client=client).review("i", "d")

    assert expected in raised.value.reason
    assert raised.value.fatal is fatal


@pytest.mark.asyncio
async def test_records_which_model_answered():
    """With refusal fallbacks, another model can answer; callers (the eval) need to know"""
    client, parse = fake_client(response(model="claude-opus-4-8"))
    model = AnthropicModel(client=client)

    await model.review("i", "d")

    assert model.served_models == {"claude-opus-4-8"}
