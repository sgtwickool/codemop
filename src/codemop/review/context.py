"""
Repository context for a review: code the diff doesn't show but the reviewer needs, found
without a model, within a token budget.

A diff shows three lines either side of each change, which misses bugs that depend on the
code around it: what a function does with the line that changed, what a constant holds, how
an imported helper behaves. For each changed file, in this order until the budget runs out:

1. The whole of each function or class with a changed line in it (for Python, found with
   the standard library's ast; for other languages, the changed lines and some either side)
2. For Python, where what the change defines (a function, a class, a constant, a model's
   field) is used, in other files or elsewhere in the same one: a change can be right in
   itself and break its callers
3. Definitions elsewhere in the same file of names the changed lines use
4. For Python, the definitions of names the file imports from the repository itself

The model is told this is reference code, not part of the change.
"""
import ast
import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Set, Tuple

from codemop.review.chunks import estimate_tokens
from codemop.review.diff import FileDiff
from codemop.review.python_code import (
    IGNORED_NAMES, changed_definitions, imported_from, innermost, module_name, module_paths, python_tree,
    references, top_level_definitions,
)

DEFAULT_CONTEXT_TOKENS = 6_000
AROUND_LINES = 25  # for languages without a parser here: this many lines either side of a change
MAX_BLOCK_LINES = 200  # a longer function or class is cut to the lines around the change
MAX_IMPORTED_FILES = 10  # repository files read for imported definitions, per review
MAX_USES = 3  # places shown where each changed definition is used
MAX_SCANNED_FILES = 2_000  # repository files searched for those places, per review
SKIPPED_FOLDERS = {"node_modules", "venv", "env", "site-packages", "__pycache__", "build", "dist"}
USE_LINES = 15  # a caller longer than twice this is cut to this many lines either side of the use


class FileSource(Protocol):
    """The repository's files as of the commit under review"""

    async def read(self, path: str) -> Optional[str]:
        """A file's text, or None if there's no such file (or it can't be read)"""
        ...

    async def paths(self) -> Sequence[str]:
        """Every file's path (empty if they can't be listed)"""
        ...


class LocalFiles:
    """Files in a directory on disk: a working copy, for a local diff"""

    def __init__(self, root: Path):
        self.root = root
        self._paths: Optional[List[str]] = None

    async def read(self, path: str) -> Optional[str]:
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root.resolve()) or not target.is_file():
            return None
        try:
            return target.read_text()
        except (OSError, UnicodeDecodeError):
            return None

    async def paths(self) -> Sequence[str]:
        if self._paths is None:  # listed once a review, not once a chunk
            self._paths = []
            # Not hidden folders, installed packages or build output; and not forever, if it's run
            # somewhere other than a repository (a home folder, say)
            for folder, folders, files in os.walk(self.root):
                folders[:] = sorted(f for f in folders if not f.startswith(".") and f not in SKIPPED_FOLDERS)
                here = Path(folder).relative_to(self.root)
                self._paths += [str(here / name) for name in sorted(files) if name.endswith(".py")]
                if len(self._paths) >= MAX_SCANNED_FILES:
                    break
        return self._paths


@dataclass(frozen=True)
class Snippet:
    path: str
    start: int
    end: int
    what: str  # e.g. "def get_db", "defines PRICE"
    code: str

    def render(self) -> str:
        """Its heading, then its lines numbered as the diff's are, so a problem in it can be pointed at"""
        width = len(str(self.end))
        numbered = (f"  {str(n).rjust(width)} | {text}" for n, text in enumerate(self.code.split("\n"), self.start))
        return f"#### {self.path}, lines {self.start}-{self.end} ({self.what})\n" + "\n".join(numbered)

    def in_diff(self, shown: Set[int]) -> bool:
        """Whether the diff already shows all of it (so it needn't be sent again)"""
        return set(range(self.start, self.end + 1)) <= shown


def changed_lines(file: FileDiff) -> Set[int]:
    return {line.new_number for hunk in file.hunks for line in hunk.lines if line.kind == "added"}


def _lines(text: str, start: int, end: int) -> str:
    return "\n".join(text.splitlines()[start - 1:end])


def _enclosing(tree: ast.Module, text: str, path: str, changed: Set[int], max_lines: int = MAX_BLOCK_LINES,
               what: str = "") -> List[Snippet]:
    """
    The innermost function or class around each of the `changed` lines (one longer than
    `max_lines` cut to the lines around it), described by `what`, or by its kind and name
    """
    found: Dict[Tuple[int, int], Snippet] = {}
    for line in sorted(changed):
        if any(s.start <= line <= s.end for s in found.values()):
            continue  # already covered by a block found for an earlier line
        block = innermost(tree, line)
        if block is None:
            continue
        start, end = block.lineno, block.end_lineno or block.lineno
        if end - start > max_lines:
            start, end = max(start, line - max_lines // 2), min(end, line + max_lines // 2)
        kind = "class" if isinstance(block, ast.ClassDef) else "def"
        found.setdefault((start, end), Snippet(path, start, end, what or f"{kind} {block.name}",
                                               _lines(text, start, end)))
    return list(found.values())


def _around(text: str, path: str, changed: Set[int]) -> List[Snippet]:
    """For other languages: the changed lines with AROUND_LINES either side, overlapping ranges merged"""
    total = len(text.splitlines())
    ranges: List[List[int]] = []
    for line in sorted(changed):
        start, end = max(1, line - AROUND_LINES), min(total, line + AROUND_LINES)
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])
    return [Snippet(path, s, e, "around the change", _lines(text, s, e)) for s, e in ranges]


def _names(text: str) -> List[str]:
    """The names in some code, in order of first use, without keywords and builtins"""
    seen = dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))
    return [name for name in seen if name not in IGNORED_NAMES]


def _names_used(file: FileDiff, blocks: Sequence[Snippet]) -> List[str]:
    """Names the change uses: on its changed lines first, then in the functions around them"""
    changed = "\n".join(line.text for hunk in file.hunks for line in hunk.lines if line.kind == "added")
    return list(dict.fromkeys(_names(changed) + _names("\n".join(b.code for b in blocks))))


def _is_test(path: str) -> bool:
    parts = Path(path).parts
    return any(part in ("test", "tests") for part in parts) or parts[-1].startswith("test_")


async def _uses(defined: Dict[str, Dict[str, str]], shown: Dict[str, Set[int]], source: FileSource) -> List[Snippet]:
    """
    Where the changed definitions are used (`defined`: by file, each name with the top-level name
    it belongs to), MAX_USES each: the function around each use, in a file that imports what it
    belongs to (or the file it's in). First elsewhere in the changed files (`shown`: the lines
    already shown, by file), then in the rest of the code, then in tests.
    """
    every_name = {name for names in defined.values() for name in names}
    paths = [p for p in await source.paths() if p.endswith(".py") and p not in shown]
    paths = [*shown, *sorted(paths, key=_is_test)][:MAX_SCANNED_FILES]
    texts = await asyncio.gather(*(source.read(path) for path in paths))
    found: Dict[str, int] = {}
    snippets: List[Snippet] = []
    for path, text in zip(paths, texts):
        tree = python_tree(text) if text and any(name in text for name in every_name) else None
        if tree is None:
            continue
        wanted = set()
        for defined_in, names in defined.items():
            imported = imported_from(tree, module_name(defined_in)) if path != defined_in else set()
            wanted |= {name for name, top in names.items()
                       if path == defined_in or top in imported or "*" in imported}
        for line, name in references(tree, wanted):
            if found.get(name, 0) >= MAX_USES or line in shown.get(path, ()):
                continue
            if any(s.path == path and s.start <= line <= s.end for s in snippets):
                continue  # already shown, for this or another name
            block = _enclosing(tree, text, path, {line}, max_lines=2 * USE_LINES, what=f"uses {name}")
            if not block:  # at the top level of the module
                start, end = max(1, line - 3), min(len(text.splitlines()), line + 3)
                block = [Snippet(path, start, end, f"uses {name}", _lines(text, start, end))]
            snippets += block
            found[name] = found.get(name, 0) + 1
    return snippets


def _definition(node: ast.stmt, name: str, text: str, path: str) -> Snippet:
    start, end = node.lineno, node.end_lineno or node.lineno
    if end - start > MAX_BLOCK_LINES:
        end = start + MAX_BLOCK_LINES
    return Snippet(path, start, end, f"defines {name}", _lines(text, start, end))


async def _imported_definitions(imported: Sequence[Tuple[str, str, str, int]], source: FileSource) -> List[Snippet]:
    """The definitions of names imported from the repository ((importer, name, module, level) each)"""
    repo_paths = set(await source.paths())
    texts: Dict[str, Optional[str]] = {}
    snippets = []
    for importer, name, module, level in imported:
        for path in module_paths(module, level, importer, repo_paths):
            if path not in texts:
                if len(texts) >= MAX_IMPORTED_FILES:
                    continue
                texts[path] = await source.read(path)
            tree = python_tree(texts[path] or "")
            node = top_level_definitions(tree).get(name) if tree else None
            if node:
                snippets.append(_definition(node, name, texts[path], path))
                break
    return snippets


async def build_context(files: Iterable[FileDiff], source: FileSource, budget_tokens: int = DEFAULT_CONTEXT_TOKENS,
                        in_diff: Optional[Mapping[str, Set[int]]] = None) -> str:
    """
    The context for the changed files, as text to put before their diff ("" if there's none).
    Nothing the diff already shows is sent again (`in_diff`: the lines it shows, by file, for
    all of it, not just these files): sent as context, changed code reads as unchanged.
    """
    files = list(files)
    if in_diff is None:
        in_diff = {file.path: file.commentable_lines() for file in files}
    snippets: List[Snippet] = []
    later: List[Snippet] = []  # same-file definitions, for step 3
    defined: Dict[str, Dict[str, str]] = {}  # what the change defines, by file, for step 2
    seen_lines: Dict[str, Set[int]] = {}  # what the diff and step 1 show, by file
    imported: List[Tuple[str, str, str, int]] = []  # (importer, name, module, level), for step 4
    files = [file for file in files if changed_lines(file)]
    texts_now = await asyncio.gather(*(source.read(file.path) for file in files))
    for file, text in zip(files, texts_now):
        if text is None:
            continue
        changed, shown = changed_lines(file), file.commentable_lines()
        tree = python_tree(text) if file.path.endswith(".py") else None
        if tree is None:
            snippets += _around(text, file.path, changed)
            continue
        blocks = _enclosing(tree, text, file.path, changed)
        snippets += blocks
        defined[file.path] = changed_definitions(tree, changed)
        seen_lines[file.path] = shown.union(*(range(b.start, b.end + 1) for b in blocks))
        used = _names_used(file, blocks)
        definitions = top_level_definitions(tree)
        imports = {alias.asname or alias.name: (alias.name, node.module or "", node.level)
                   for node in tree.body if isinstance(node, ast.ImportFrom) for alias in node.names}
        for name in used:  # in order of importance
            node = definitions.get(name)
            if node and not any(b.start <= node.lineno <= b.end for b in blocks):
                later.append(_definition(node, name, text, file.path))
            elif name in imports:
                imported.append((file.path, *imports[name]))
    # Imported definitions are read first: without a snapshot of the repository, reads are limited
    imports = await _imported_definitions(imported, source) if imported else []
    snippets += await _uses(defined, seen_lines, source) if any(defined.values()) else []
    snippets += later + imports

    parts, used_tokens, seen = [], 0, set()
    for snippet in snippets:
        if (snippet.path, snippet.start, snippet.end) in seen or snippet.in_diff(in_diff.get(snippet.path, set())):
            continue
        rendered = snippet.render()
        tokens = estimate_tokens(rendered)
        if used_tokens + tokens > budget_tokens:
            continue  # a smaller one later may still fit
        parts.append(rendered)
        used_tokens += tokens
        seen.add((snippet.path, snippet.start, snippet.end))
    if not parts:
        return ""
    return "### Context: unchanged code from the repository, for reference (not part of the change)\n\n" + "\n\n".join(parts)
