"""
Reviewing a whole diff: chunk it, review the chunks concurrently, and gather one report
that says what was reviewed and what wasn't, and why.
"""
import asyncio
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Sequence

from codemop.config import DEFAULT_MIN_CONFIDENCE
from codemop.providers.base import NoReview, NoReviewKind, ReviewModel, Usage
from codemop.review.chunks import DEFAULT_IGNORED_PATHS, Skipped, plan_chunks
from codemop.review.context import DEFAULT_CONTEXT_TOKENS, FileSource, build_context
from codemop.review.diff import parse_diff
from codemop.review.fixes import fit_fix
from codemop.review.learned import Settled
from codemop.review.placement import Unplaced, place_suggestions
from codemop.review.prompt import SYSTEM_PROMPT
from codemop.review.schema import ModelSuggestion

DEFAULT_CONCURRENCY = 4


@dataclass(frozen=True)
class FailedChunk:
    paths: List[str]
    reason: str
    kind: NoReviewKind | Literal["not_reviewed"] = "error"  # not_reviewed: skipped after a fatal error


@dataclass(frozen=True)
class DroppedFix:
    """A suggested fix left out because it doesn't fit its lines (the suggestion is kept)"""
    file_path: str
    line: int
    reason: str


@dataclass
class ReviewReport:
    model: str
    suggestions: List[ModelSuggestion] = field(default_factory=list)
    unplaced: List[Unplaced] = field(default_factory=list)  # suggestions on lines GitHub can't comment on
    below_confidence: int = 0  # suggestions dropped by min_confidence
    already_dismissed: int = 0  # suggestions dropped because someone dismissed them earlier on the PR
    dropped_fixes: List[DroppedFix] = field(default_factory=list)  # fixes that would have duplicated code
    skipped: List[Skipped] = field(default_factory=list)  # parts of the diff not reviewed
    failed: List[FailedChunk] = field(default_factory=list)  # chunks the model gave no review for
    stopped: Optional[str] = None  # why the review stopped early, if it did
    too_large: Optional[str] = None  # why nothing was reviewed: more changed lines than max_changed_lines
    chunks: int = 0
    usage: Usage = Usage()
    cost: Optional[float] = None  # estimated US dollars at list prices; None if unknown

    def notes(self, code=lambda text: text) -> List[str]:
        """What was skipped, set aside or left out, and why (`code` formats paths, e.g. in backticks)"""
        notes = [f"Skipped {code(s.path)}: {s.reason}" for s in self.skipped]
        if self.unplaced:
            notes.append(f"Set aside {len(self.unplaced)} suggestion(s) that pointed at lines outside the diff")
        if self.below_confidence:
            notes.append(f"Dropped {self.below_confidence} suggestion(s) below the confidence threshold")
        if self.already_dismissed:
            notes.append(f"Left out {self.already_dismissed} suggestion(s) dismissed earlier on this pull request")
        notes += [f"Left out the suggested fix for {code(f'{d.file_path}:{d.line}')}: {d.reason}"
                  for d in self.dropped_fixes]
        return notes

    @property
    def complete(self) -> bool:
        """Every reviewable part of the diff got a review"""
        return not self.failed and self.stopped is None and self.too_large is None


async def review_diff(
    diff: str,
    model: ReviewModel,
    *,
    chunk_tokens: Optional[int] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    ignored_paths: Sequence[str] = DEFAULT_IGNORED_PATHS,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    max_changed_lines: Optional[int] = None,
    settled: Settled = Settled(),
    context: Optional[FileSource] = None,
    context_tokens: int = DEFAULT_CONTEXT_TOKENS,
) -> ReviewReport:
    """
    Review a unified diff with `model` (chunk_tokens defaults to the model's own chunk size).
    With max_changed_lines, a diff with more added and removed lines to review than that
    isn't sent to the model at all (a cost limit). `settled` is what the model is told not to
    raise again (and dismissed issues it raises anyway are dropped). With `context`, the
    repository's files at the commit under review, each chunk comes with the code around and
    beneath its changes (up to context_tokens, or half the chunk size if that's less).
    """
    instructions = SYSTEM_PROMPT + settled.instructions()
    plan_budget = chunk_tokens or model.chunk_tokens
    files = parse_diff(diff)
    plan = plan_chunks(files, plan_budget, ignored_paths=ignored_paths)
    in_diff = {file.path: file.commentable_lines() for file in files}  # for context, which mustn't repeat it
    report = ReviewReport(model=model.name, skipped=list(plan.skipped), chunks=len(plan.chunks))
    changed = sum(
        line.kind != "context"
        for chunk in plan.chunks for file in chunk.files for hunk in file.hunks for line in hunk.lines
    )
    if max_changed_lines is not None and changed > max_changed_lines:
        report.too_large = f"{changed:,} changed lines to review, more than the limit of {max_changed_lines:,}"
        report.cost = model.cost(report.usage)
        return report
    limit = asyncio.Semaphore(concurrency)

    async def review_chunk(chunk):
        async with limit:
            paths = [file.path for file in chunk.files]
            if report.stopped:
                report.failed.append(FailedChunk(paths, f"not reviewed: {report.stopped}", "not_reviewed"))
                return
            text = chunk.text
            if context is not None:
                around = await build_context(chunk.files, context, min(context_tokens, plan_budget // 2), in_diff)
                text = f"{around}\n\n### The change\n\n{chunk.text}" if around else chunk.text
            try:
                review, usage = await model.review(instructions, text)
            except NoReview as e:
                report.usage += e.usage
                report.failed.append(FailedChunk(paths, e.reason, e.kind))
                if e.fatal and not report.stopped:
                    report.stopped = e.reason
                return
            report.usage += usage
            placement = place_suggestions(review.suggestions, chunk.files)
            report.unplaced.extend(placement.unplaced)
            shown = {file.path: file.new_lines() for file in chunk.files}
            for suggestion in placement.placed:
                if suggestion.confidence < min_confidence:
                    report.below_confidence += 1
                    continue
                if settled.dismisses(suggestion):
                    report.already_dismissed += 1
                    continue
                fix, problem = fit_fix(suggestion, shown[suggestion.file_path])
                if problem:
                    report.dropped_fixes.append(DroppedFix(suggestion.file_path, suggestion.line, problem))
                if fix != suggestion.suggested_code:
                    suggestion = suggestion.model_copy(update={"suggested_code": fix})
                report.suggestions.append(suggestion)

    await asyncio.gather(*(review_chunk(chunk) for chunk in plan.chunks))
    report.suggestions.sort(key=lambda s: (s.file_path, s.line))
    report.cost = model.cost(report.usage)
    return report
