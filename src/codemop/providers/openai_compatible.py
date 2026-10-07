"""
Any provider with an OpenAI-compatible chat completions API: Mistral, OpenAI, OpenRouter,
and local models through Ollama or vLLM.

The review schema is requested with response_format "json_schema". Not every provider
enforces it strictly, so the answer is validated here, and an invalid one gets a single
repair attempt with the validation errors before giving up.
"""
import asyncio
import json
import os
from dataclasses import dataclass
from typing import Optional

import httpx
import pydantic

from codemop.providers.base import NoReview, Usage
from codemop.review.schema import ModelReview


@dataclass(frozen=True)
class Preset:
    base_url: str
    key_env: Optional[str]  # None: no key needed


PRESETS = {
    "openai": Preset("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "mistral": Preset("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "openrouter": Preset("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": Preset("http://localhost:11434/v1", None),
}

RETRY_STATUSES = {408, 409, 429, 500, 502, 503, 504}
REPAIR_INSTRUCTION = (
    "That reply didn't match the required JSON schema:\n{errors}\n"
    "Reply again with only the corrected JSON object."
)


class OpenAICompatibleModel:
    """A ReviewModel for any OpenAI-compatible chat completions API"""

    def __init__(
        self,
        model: str,
        *,
        provider: str = "openai",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        key_env: Optional[str] = None,
        max_output_tokens: int = 16000,
        max_retries: int = 2,
        timeout: float = 300.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        preset = PRESETS.get(provider, Preset("", None))
        self.model = model
        self.provider = provider
        self.base_url = (base_url or preset.base_url).rstrip("/")
        if not self.base_url:
            raise ValueError(f"Unknown provider {provider!r}: give a base_url")
        self.key_env = key_env or preset.key_env
        self.api_key = api_key or (os.environ.get(self.key_env) if self.key_env else None)
        self.max_output_tokens = max_output_tokens
        self.max_retries = max_retries
        self.timeout = timeout
        self._transport = transport

    @property
    def name(self) -> str:
        return f"{self.provider}/{self.model}"

    def _key_hint(self) -> str:
        return f"check {self.key_env} is set to a valid key" if self.key_env else "check the API key"

    async def _complete(self, client: httpx.AsyncClient, messages: list) -> tuple[dict, Usage]:
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "review", "schema": ModelReview.model_json_schema()},
            },
        }
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.post("/chat/completions", json=body)
            except httpx.TransportError:
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise NoReview(f"Couldn't connect to {self.base_url}; check the network and base URL")
            if response.status_code in RETRY_STATUSES and attempt < self.max_retries:
                await asyncio.sleep(2 ** attempt)
                continue
            break

        status = response.status_code
        if status in (401, 403):
            raise NoReview(f"{self.provider} rejected the API key: {self._key_hint()}", fatal=True)
        if status == 404:
            raise NoReview(f"Model {self.model} wasn't found at {self.base_url}", fatal=True)
        if status == 429:
            raise NoReview(f"{self.provider} rate limit reached (after retries); try again later")
        if status == 400 and "response_format" in response.text:
            raise NoReview(
                f"{self.name} doesn't support structured output (response_format json_schema)",
                fatal=True,
            )
        if status >= 400:
            raise NoReview(f"{self.provider} returned an error ({status}): {response.text[:200]}")

        data = response.json()
        usage = data.get("usage") or {}
        return data, Usage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    async def review(self, instructions: str, diff_text: str) -> tuple[ModelReview, Usage]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        messages = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": diff_text},
        ]
        total = Usage()
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=self.timeout, transport=self._transport
        ) as client:
            for attempt in range(2):  # the answer, then one repair attempt
                data, usage = await self._complete(client, messages)
                total += usage
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}

                if message.get("refusal") or choice.get("finish_reason") == "content_filter":
                    raise NoReview(f"{self.name} declined to review this part of the diff", usage=total)
                if choice.get("finish_reason") == "length":
                    raise NoReview(
                        f"{self.name}'s review was cut off at {self.max_output_tokens} output tokens; "
                        "raise the output limit or use smaller chunks",
                        usage=total,
                    )

                content = message.get("content") or ""
                try:
                    return ModelReview.model_validate_json(content), total
                except pydantic.ValidationError as e:
                    errors = json.dumps(e.errors(include_url=False, include_context=False), default=str)[:2000]
                    messages += [
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": REPAIR_INSTRUCTION.format(errors=errors)},
                    ]

        raise NoReview(f"{self.name} returned a review that doesn't match the schema, even after a retry", usage=total)
