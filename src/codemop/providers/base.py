"""
The interface every model provider implements.

The review code only talks to a ReviewModel; provider SDKs and HTTP details stay inside
their adapter modules.
"""
from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from codemop.review.schema import ModelReview


@dataclass(frozen=True)
class Usage:
    """Tokens used by one or more requests"""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )


# Why a chunk got no review: the model declined, its answer hit the output limit, or
# something else went wrong (the reason says what)
NoReviewKind = Literal["refused", "cut_off", "error"]


class NoReview(Exception):
    """
    The model gave no usable review. The message says why, and what to do about it.

    `fatal` means every request would fail the same way (a rejected key, an unknown model),
    so the rest of the review should stop rather than repeat it.
    """

    def __init__(self, reason: str, *, fatal: bool = False, usage: Usage = Usage(), kind: NoReviewKind = "error"):
        super().__init__(reason)
        self.reason = reason
        self.fatal = fatal
        self.usage = usage
        self.kind = kind

    @classmethod
    def refused(cls, model_name: str, usage: Usage, detail: str = "") -> "NoReview":
        return cls(f"{model_name} declined to review this part of the diff{detail}", usage=usage, kind="refused")

    @classmethod
    def cut_off(cls, model_name: str, max_output_tokens: int, usage: Usage) -> "NoReview":
        return cls(
            f"{model_name}'s review was cut off at {max_output_tokens} output tokens; "
            "raise the output limit or use smaller chunks",
            usage=usage, kind="cut_off",
        )


# Largest piece of diff to send in one request, unless a model says otherwise
DEFAULT_CHUNK_TOKENS = 40_000


class ReviewModel(Protocol):
    """A model that can review one chunk of a diff"""

    #: The largest piece of diff this model should be sent at once, in tokens
    chunk_tokens: int

    @property
    def name(self) -> str:
        """provider/model, e.g. anthropic/claude-opus-5-5"""
        ...

    async def review(self, instructions: str, diff_text: str) -> tuple[ModelReview, Usage]:
        """Review `diff_text` following `instructions`; raises NoReview if there's no usable answer"""
        ...

    def cost(self, usage: Usage) -> Optional[float]:
        """Estimated US dollars for `usage` at list prices, or None if the price isn't known"""
        ...
