"""
Repository context for a review: code the diff doesn't show but the reviewer needs, found
without a model, within a token budget.

A diff shows three lines either side of each change, which misses bugs that depend on the
code around it: what a function does with the line that changed, what a constant holds, how
an imported helper behaves. For each changed file, in this order until the budget runs out:

1. The whole of each function or class with a changed line in it
2. Where what the change defines (a function, a class, a constant, a model's or an
   interface's field) is used, in other files or elsewhere in the same one: a change can be
   right in itself and break its callers
3. Definitions elsewhere in the same file of names the changed lines use
4. The definitions of names the file imports from the repository itself

That's for Python, TypeScript and JavaScript (codemop.review.code reads them); any other
language gets the changed lines and some either side.

The model is told this is reference code, not part of the change.
"""
import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Set, Tuple

from codemop.review.chunks import estimate_tokens
from codemop.review.diff import FileDiff
from codemop.review.code import Block, Import, Parsed, language_for

DEFAULT_CONTEXT_TOKENS = 6_000
AROUND_LINES = 25  # for languages without a parser here: this many lines either side of a change
MAX_BLOCK_LINES = 200  # a longer function or class is cut to the lines around the change
MAX_IMPORTED_FILES = 10  # repository files read for imported definitions, per review
MAX_USES = 3  # places shown where each changed definition is used
MAX_SCANNED_FILES = 2_000  # repository files searched for those places, per review
SKIPPED_FOLDERS = {"node_modules", "venv", "env", "site-packages", "__pycache__", "build", "dist", "coverage"}
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
                self._paths += [str(here / name) for name in sorted(files) if language_for(name)]
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


def _enclosing(code: Parsed, text: str, path: str, changed: Set[int], max_lines: int = MAX_BLOCK_LINES,
               what: str = "") -> List[Snippet]:
    """
    The innermost function or class around each of the `changed` lines (one longer than
    `max_lines` cut to the lines around it), described by `what`, or by its kind and name
    """
    found: Dict[Tuple[int, int], Snippet] = {}
    for line in sorted(changed):
        if any(s.start <= line <= s.end for s in found.values()):
            continue  # already covered by a block found for an earlier line
        block = code.innermost(line)
        if block is None:
            continue
        start, end = block.start, block.end
        if end - start > max_lines:
            start, end = max(start, line - max_lines // 2), min(end, line + max_lines // 2)
        found.setdefault((start, end), Snippet(path, start, end, what or f"{block.kind} {block.name}",
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


def _names(text: str, ignored: Set[str]) -> List[str]:
    """The names in some code, in order of first use, without keywords and built-ins"""
    seen = dict.fromkeys(re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", text))
    return [name for name in seen if name not in ignored]


def _names_used(file: FileDiff, blocks: Sequence[Snippet], ignored: Set[str]) -> List[str]:
    """Names the change uses: on its changed lines first, then in the functions around them"""
    changed = "\n".join(line.text for hunk in file.hunks for line in hunk.lines if line.kind == "added")
    return list(dict.fromkeys(_names(changed, ignored) + _names("\n".join(b.code for b in blocks), ignored)))


def _is_test(path: str) -> bool:
    parts = Path(path).parts
    name = parts[-1]
    return (any(part in ("test", "tests", "__tests__", "e2e") for part in parts) or name.startswith("test_")
            or bool(re.search(r"\.(test|spec)\.[^.]+$", name)))


async def _uses(defined: Dict[str, Dict[str, Set[str]]], shown: Dict[str, Set[int]],
                source: FileSource) -> List[Snippet]:
    """
    Where the changed definitions are used (`defined`: by file, each name with the names a file
    can import to use it), MAX_USES each: the function around each use, in a file in the same
    language that imports one of those names (or the file it's in). First elsewhere in the
    changed files (`shown`: the lines already shown, by file), then in the rest of the code,
    then in tests.
    """
    languages = {path: language_for(path) for path in defined}
    modules = {path: languages[path].module_name(path) for path in defined}
    every_name = {name for names in defined.values() for name in names}
    paths = [p for p in await source.paths() if p not in shown and language_for(p) in languages.values()]
    paths = [*shown, *sorted(paths, key=_is_test)][:MAX_SCANNED_FILES]
    texts = await asyncio.gather(*(source.read(path) for path in paths))
    found: Dict[str, int] = {}
    snippets: List[Snippet] = []
    for path, text in zip(paths, texts):
        if all(found.get(name, 0) >= MAX_USES for name in every_name):
            break
        language = language_for(path)
        # Cheap checks before parsing: a file can only use them if it names them, and only from
        # another file if it imports that file (whose module name is then in it too)
        if not text or language is None or not any(name in text for name in every_name):
            continue
        if path not in defined and not any(module in text for module in modules.values()):
            continue
        code = language.parse(path, text)
        if code is None:
            continue
        wanted = set()
        for defined_in, names in defined.items():
            if languages[defined_in] is not language:
                continue
            if path == defined_in:
                wanted |= set(names)
                continue
            imported = code.imported_from(modules[defined_in])
            wanted |= {name for name, importable in names.items() if importable & imported or "*" in imported}
        for line, name in code.references(wanted) if wanted else []:
            if found.get(name, 0) >= MAX_USES or line in shown.get(path, ()):
                continue
            if any(s.path == path and s.start <= line <= s.end for s in snippets):
                continue  # already shown, for this or another name
            block = _enclosing(code, text, path, {line}, max_lines=2 * USE_LINES, what=f"uses {name}")
            if not block:  # at the top level of the module
                start, end = max(1, line - 3), min(len(text.splitlines()), line + 3)
                block = [Snippet(path, start, end, f"uses {name}", _lines(text, start, end))]
            snippets += block
            found[name] = found.get(name, 0) + 1
    return snippets


def _definition(block: Block, name: str, text: str, path: str) -> Snippet:
    start, end = block.start, min(block.end, block.start + MAX_BLOCK_LINES)
    return Snippet(path, start, end, f"defines {name}", _lines(text, start, end))


async def _imported_definitions(imported: Sequence[Tuple[str, Import]], source: FileSource) -> List[Snippet]:
    """The definitions of names imported from the repository (each with the file importing it)"""
    repo_paths = set(await source.paths())
    texts: Dict[str, Optional[str]] = {}
    snippets = []
    for importer, (name, origin) in imported:
        language = language_for(importer)
        for path in language.module_paths(origin, importer, repo_paths):
            if path not in texts:
                if len(texts) >= MAX_IMPORTED_FILES:
                    continue
                texts[path] = await source.read(path)
            text = texts[path]
            code = language.parse(path, text) if text else None
            block = code.top_level_definitions().get(name) if code else None
            if block:
                snippets.append(_definition(block, name, text, path))
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
    defined: Dict[str, Dict[str, Set[str]]] = {}  # what the change defines, by file, for step 2
    seen_lines: Dict[str, Set[int]] = {}  # what the diff and step 1 show, by file
    imported: List[Tuple[str, Import]] = []  # what the changed files import, by importer, for step 4
    files = [file for file in files if changed_lines(file)]
    texts_now = await asyncio.gather(*(source.read(file.path) for file in files))
    for file, text in zip(files, texts_now):
        if text is None:
            continue
        changed, shown = changed_lines(file), file.commentable_lines()
        language = language_for(file.path)
        code = language.parse(file.path, text) if language else None
        if code is None:
            snippets += _around(text, file.path, changed)
            continue
        blocks = _enclosing(code, text, file.path, changed)
        snippets += blocks
        defined[file.path] = code.changed_definitions(changed)
        seen_lines[file.path] = shown.union(*(range(b.start, b.end + 1) for b in blocks))
        definitions, imports = code.top_level_definitions(), code.imports()
        for name in _names_used(file, blocks, language.ignored):  # in order of importance
            block = definitions.get(name)
            if block and not any(b.start <= block.start <= b.end for b in blocks):
                later.append(_definition(block, name, text, file.path))
            elif name in imports:
                imported.append((file.path, imports[name]))
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
