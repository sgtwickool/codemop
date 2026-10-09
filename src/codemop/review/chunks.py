"""
Splitting a diff into chunks that each fit in one model request.

Files are packed together up to a token budget. A file too big for one chunk is split by
hunk, and anything that still doesn't fit, or isn't worth reviewing (lock files, binaries,
deletions), is skipped with a reason, so a large PR is never silently cut short.
"""
import math
from dataclasses import dataclass, field, replace
from fnmatch import fnmatch
from typing import Callable, Iterable, List, Sequence

from codemop.review.diff import FileDiff, Hunk
from codemop.review.prompt import render_hunks

# Generated files that are rarely worth reviewing
DEFAULT_IGNORED_PATHS = (
    "*.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "go.sum",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.svg",
)


def estimate_tokens(text: str) -> int:
    """A deliberately high estimate (code averages more than 3 characters per token)"""
    return math.ceil(len(text) / 3)


@dataclass
class Chunk:
    """Part of the diff, rendered for the model, and the files it shows (with only the hunks it shows)"""
    files: List[FileDiff] = field(default_factory=list)
    parts: List[str] = field(default_factory=list)
    tokens: int = 0

    @property
    def text(self) -> str:
        return "\n\n".join(self.parts)


@dataclass(frozen=True)
class Skipped:
    path: str
    reason: str


@dataclass
class ChunkPlan:
    chunks: List[Chunk]
    skipped: List[Skipped]


def is_ignored(path: str, patterns: Sequence[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch(path, pattern) or fnmatch(name, pattern) for pattern in patterns)


def _skip_reason(file: FileDiff, ignored_paths: Sequence[str]) -> str | None:
    if file.status == "deleted":
        return "deleted file"
    if file.is_binary:
        return "binary file"
    if not file.hunks:
        return "no changed lines" + (" (rename only)" if file.status == "renamed" else "")
    if is_ignored(file.path, ignored_paths):
        return "matches an ignored path pattern"
    return None


def _pieces(
    file: FileDiff, budget: int, count_tokens: Callable[[str], int], skipped: List[Skipped]
) -> Iterable[tuple[str, int, List[Hunk]]]:
    """The file as one rendered piece if it fits, otherwise its hunks packed into pieces"""
    whole = render_hunks(file, file.hunks)
    whole_tokens = count_tokens(whole)
    if whole_tokens <= budget:
        yield whole, whole_tokens, list(file.hunks)
        return

    group: List[Hunk] = []
    for hunk in file.hunks:
        if count_tokens(render_hunks(file, [hunk])) > budget:
            skipped.append(Skipped(file.path, f"hunk too large to review: {hunk.header}"))
            continue
        if group and count_tokens(render_hunks(file, group + [hunk])) > budget:
            rendered = render_hunks(file, group)
            yield rendered, count_tokens(rendered), group
            group = []
        group.append(hunk)
    if group:
        rendered = render_hunks(file, group)
        yield rendered, count_tokens(rendered), group


def plan_chunks(
    files: Sequence[FileDiff],
    budget_tokens: int,
    count_tokens: Callable[[str], int] = estimate_tokens,
    ignored_paths: Sequence[str] = DEFAULT_IGNORED_PATHS,
) -> ChunkPlan:
    """Pack the reviewable parts of a diff into chunks of at most `budget_tokens` each"""
    chunks: List[Chunk] = []
    skipped: List[Skipped] = []
    current = Chunk()

    for file in files:
        reason = _skip_reason(file, ignored_paths)
        if reason:
            skipped.append(Skipped(file.path, reason))
            continue
        for rendered, tokens, hunks in _pieces(file, budget_tokens, count_tokens, skipped):
            if current.parts and current.tokens + tokens > budget_tokens:
                chunks.append(current)
                current = Chunk()
            current.parts.append(rendered)
            current.tokens += tokens
            # Only the hunks shown, so suggestions can only be placed on lines the model saw
            shown = next((f for f in current.files if f.path == file.path), None)
            if shown:
                shown.hunks.extend(hunks)
            else:
                current.files.append(replace(file, hunks=list(hunks)))

    if current.parts:
        chunks.append(current)
    return ChunkPlan(chunks=chunks, skipped=skipped)
