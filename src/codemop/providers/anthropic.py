"""
Claude, through the official Anthropic SDK.

Uses structured output (messages.parse with the review schema), so Claude's answer is
constrained to the schema and validated on the way back.
"""
from typing import Optional

import anthropic
import pydantic

from codemop.providers.base import NoReview, Usage
from codemop.review.schema import ModelReview

DEFAULT_MODEL = "claude-opus-5-5"

# Models that accept fallbacks="default": if the model declines a request, the API re-runs it
# on Anthropic's recommended model for that refusal category instead of returning a refusal
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_DEFAULT_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}

# Older models reject the effort setting
_NO_EFFORT_PREFIXES = ("claude-haiku-", "claude-sonnet-4-5", "claude-3")

KEY_HINT = "check ANTHROPIC_API_KEY is set to a valid key"


class AnthropicModel:
    """A ReviewModel backed by Claude"""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        api_key: Optional[str] = None,
        effort: Optional[str] = "high",
        max_output_tokens: int = 16000,
        client: Optional[anthropic.AsyncAnthropic] = None,
    ):
        self.model = model
        self.effort = None if model.startswith(_NO_EFFORT_PREFIXES) else effort
        self.max_output_tokens = max_output_tokens
        # With no api_key the SDK finds credentials itself (ANTHROPIC_API_KEY, `ant auth login`...)
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def name(self) -> str:
        return f"anthropic/{self.model}"

    async def review(self, instructions: str, diff_text: str) -> tuple[ModelReview, Usage]:
        request = dict(
            model=self.model,
            max_tokens=self.max_output_tokens,
            system=instructions,
            messages=[{"role": "user", "content": diff_text}],
            output_format=ModelReview,
        )
        if self.effort:
            request["output_config"] = {"effort": self.effort}

        try:
            if self.model in _DEFAULT_FALLBACK_MODELS:
                response = await self._client.beta.messages.parse(
                    betas=[_FALLBACK_BETA], fallbacks="default", **request
                )
            else:
                response = await self._client.messages.parse(**request)
        except pydantic.ValidationError:
            raise NoReview(f"{self.name} returned a review that doesn't match the schema")
        except anthropic.AuthenticationError:
            raise NoReview(f"Anthropic rejected the API key: {KEY_HINT}", fatal=True)
        except anthropic.PermissionDeniedError:
            raise NoReview(f"The Anthropic API key isn't allowed to use {self.model}", fatal=True)
        except anthropic.NotFoundError:
            raise NoReview(f"Model {self.model} wasn't found, or isn't available to this API key", fatal=True)
        except anthropic.RateLimitError:
            raise NoReview("Anthropic rate limit reached (after retries); try again later")
        except anthropic.BadRequestError as e:
            raise NoReview(f"Anthropic rejected the request: {e.message}")
        except anthropic.APIStatusError as e:
            raise NoReview(f"Anthropic returned an error ({e.status_code}); try again later")
        except anthropic.APIConnectionError:
            raise NoReview("Couldn't connect to the Anthropic API; check the network")

        usage = Usage(
            input_tokens=response.usage.input_tokens or 0,
            output_tokens=response.usage.output_tokens or 0,
            cache_read_tokens=response.usage.cache_read_input_tokens or 0,
            cache_write_tokens=response.usage.cache_creation_input_tokens or 0,
        )
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            detail = f" ({category})" if category else ""
            raise NoReview(f"{self.name} declined to review this part of the diff{detail}", usage=usage)
        if response.stop_reason == "max_tokens":
            raise NoReview(
                f"{self.name}'s review was cut off at {self.max_output_tokens} output tokens; "
                "raise the output limit or use smaller chunks",
                usage=usage,
            )
        if response.parsed_output is None:
            raise NoReview(f"{self.name} returned no review", usage=usage)
        return response.parsed_output, usage
