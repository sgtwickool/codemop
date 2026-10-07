"""
Reviewing a whole diff: chunk it, review the chunks concurrently, and gather one report
that says what was reviewed and what wasn't, and why.
"""
import asyncio
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from codemop.providers.base import NoReview, ReviewModel, Usage
from codemop.review.chunks import DEFAULT_IGNORED_PATHS, Skipped, plan_chunks
from codemop.review.diff import parse_diff
from codemop.review.placement import Unplaced, place_suggestions
from codemop.review.prompt import SYSTEM_PROMPT
from codemop.review.schema import ModelSuggestion

DEFAULT_CONCURRENCY = 4


@dataclass(frozen=True)
class FailedChunk:
    paths: List[str]
    reason: str


@dataclass
class ReviewReport:
    model: str
    suggestions: List[ModelSuggestion] = field(default_factory=list)
    unplaced: List[Unplaced] = field(default_factory=list)  # suggestions on lines GitHub can't comment on
    below_confidence: int = 0  # suggestions dropped by min_confidence
    skipped: List[Skipped] = field(default_factory=list)  # parts of the diff not reviewed
    failed: List[FailedChunk] = field(default_factory=list)  # chunks the model gave no review for
    stopped: Optional[str] = None  # why the review stopped early, if it did
    chunks: int = 0
    usage: Usage = Usage()

    @property
    def complete(self) -> bool:
        """Every reviewable part of the diff got a review"""
        return not self.failed and self.stopped is None


async def review_diff(
    diff: str,
    model: ReviewModel,
    *,
    chunk_tokens: Optional[int] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    ignored_paths: Sequence[str] = DEFAULT_IGNORED_PATHS,
    min_confidence: float = 0.0,
) -> ReviewReport:
    """Review a unified diff with `model` (chunk_tokens defaults to the model's own chunk size)"""
    plan = plan_chunks(parse_diff(diff), chunk_tokens or model.chunk_tokens, ignored_paths=ignored_paths)
    report = ReviewReport(model=model.name, skipped=list(plan.skipped), chunks=len(plan.chunks))
    limit = asyncio.Semaphore(concurrency)

    async def review_chunk(chunk):
        async with limit:
            paths = [file.path for file in chunk.files]
            if report.stopped:
                report.failed.append(FailedChunk(paths, f"not reviewed: {report.stopped}"))
                return
            try:
                review, usage = await model.review(SYSTEM_PROMPT, chunk.text)
            except NoReview as e:
                report.usage += e.usage
                report.failed.append(FailedChunk(paths, e.reason))
                if e.fatal and not report.stopped:
                    report.stopped = e.reason
                return
            report.usage += usage
            placement = place_suggestions(review.suggestions, chunk.files)
            report.unplaced.extend(placement.unplaced)
            for suggestion in placement.placed:
                if suggestion.confidence >= min_confidence:
                    report.suggestions.append(suggestion)
                else:
                    report.below_confidence += 1

    await asyncio.gather(*(review_chunk(chunk) for chunk in plan.chunks))
    report.suggestions.sort(key=lambda s: (s.file_path, s.line))
    return report
