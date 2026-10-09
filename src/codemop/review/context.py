"""
Repository context for a review: code the diff doesn't show but the reviewer needs, found
without a model, within a token budget.

A diff shows three lines either side of each change, which misses bugs that depend on the
code around it: what a function does with the line that changed, what a constant holds, how
an imported helper behaves. For each changed file, in this order until the budget runs out:

1. The whole of each function or class with a changed line in it (for Python, found with
   the standard library's ast; for other languages, the changed lines and some either side)
2. Definitions elsewhere in the same file of names the changed lines use
3. For Python, the definitions of names the file imports from the repository itself

The model is told this is reference code, not part of the change.
"""
import ast
import builtins
import keyword
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Protocol, Sequence, Set, Tuple

from codemop.review.chunks import estimate_tokens
from codemop.review.diff import FileDiff

DEFAULT_CONTEXT_TOKENS = 6_000
AROUND_LINES = 25  # for languages without a parser here: this many lines either side of a change
MAX_BLOCK_LINES = 200  # a longer function or class is cut to the lines around the change
MAX_IMPORTED_FILES = 10  # repository files read for imported definitions, per review
_IGNORED_NAMES = set(keyword.kwlist) | set(dir(builtins)) | {"self", "cls"}


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

    async def read(self, path: str) -> Optional[str]:
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root.resolve()) or not target.is_file():
            return None
        try:
            return target.read_text()
        except (OSError, UnicodeDecodeError):
            return None

    async def paths(self) -> Sequence[str]:
        return [str(p.relative_to(self.root)) for p in self.root.rglob("*.py")
                if p.is_file() and not any(part.startswith(".") for part in p.relative_to(self.root).parts)]


@dataclass(frozen=True)
class Snippet:
    path: str
    start: int
    end: int
    what: str  # e.g. "def get_db", "defines PRICE"
    code: str

    def render(self) -> str:
        return f"#### {self.path}, lines {self.start}-{self.end} ({self.what})\n{self.code}"


def changed_lines(file: FileDiff) -> Set[int]:
    return {line.new_number for hunk in file.hunks for line in hunk.lines if line.kind == "added"}


def shown_lines(file: FileDiff) -> Set[int]:
    """The new-file lines the diff already shows (added or unchanged)"""
    return {line.new_number for hunk in file.hunks for line in hunk.lines if line.new_number is not None}


def _lines(text: str, start: int, end: int) -> str:
    return "\n".join(text.splitlines()[start - 1:end])


def _python_tree(text: str) -> Optional[ast.Module]:
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


def _enclosing(tree: ast.Module, text: str, path: str, changed: Set[int]) -> List[Snippet]:
    """The innermost function or class around each changed line"""
    blocks = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    found: Dict[Tuple[int, int], Snippet] = {}
    for line in sorted(changed):
        if any(s.start <= line <= s.end for s in found.values()):
            continue  # already covered by a block found for an earlier line
        around = [b for b in blocks if b.lineno <= line <= (b.end_lineno or b.lineno)]
        if not around:
            continue
        block = min(around, key=lambda b: (b.end_lineno or b.lineno) - b.lineno)
        start, end = block.lineno, block.end_lineno or block.lineno
        if end - start > MAX_BLOCK_LINES:
            start, end = max(start, line - MAX_BLOCK_LINES // 2), min(end, line + MAX_BLOCK_LINES // 2)
        kind = "class" if isinstance(block, ast.ClassDef) else "def"
        found.setdefault((start, end), Snippet(path, start, end, f"{kind} {block.name}", _lines(text, start, end)))
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
    return [name for name in seen if name not in _IGNORED_NAMES]


def _names_used(file: FileDiff, blocks: Sequence[Snippet]) -> List[str]:
    """Names the change uses: on its changed lines first, then in the functions around them"""
    changed = "\n".join(line.text for hunk in file.hunks for line in hunk.lines if line.kind == "added")
    return list(dict.fromkeys(_names(changed) + _names("\n".join(b.code for b in blocks))))


def _top_level_definitions(tree: ast.Module) -> Dict[str, ast.stmt]:
    definitions = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    definitions[target.id] = node
    return definitions


def _definition(node: ast.stmt, name: str, text: str, path: str) -> Snippet:
    start, end = node.lineno, node.end_lineno or node.lineno
    if end - start > MAX_BLOCK_LINES:
        end = start + MAX_BLOCK_LINES
    return Snippet(path, start, end, f"defines {name}", _lines(text, start, end))


def _module_paths(module: str, level: int, importer: str, repo_paths: Set[str]) -> List[str]:
    """Repository files a `from module import ...` in `importer` could mean"""
    if level:  # relative: from the importing file's package
        base = Path(importer).parent
        for _ in range(level - 1):
            base = base.parent
        stem = str(base / module.replace(".", "/")) if module else str(base)
        candidates = [f"{stem}.py", f"{stem}/__init__.py"]
        return [c.removeprefix("./") for c in candidates if c.removeprefix("./") in repo_paths]
    tail = module.replace(".", "/")
    return sorted(p for p in repo_paths if p == f"{tail}.py" or p.endswith(f"/{tail}.py")
                  or p == f"{tail}/__init__.py" or p.endswith(f"/{tail}/__init__.py"))


async def build_context(files: Iterable[FileDiff], source: FileSource,
                        budget_tokens: int = DEFAULT_CONTEXT_TOKENS) -> str:
    """The context for the changed files, as text to put before their diff ("" if there's none)"""
    snippets: List[Snippet] = []
    later: List[Snippet] = []  # same-file definitions, after every file's changed blocks
    imported: List[Tuple[str, str, str, int]] = []  # (importer, name, module, level), for step 3
    for file in files:
        changed = changed_lines(file)
        text = await source.read(file.path) if changed else None
        if text is None:
            continue
        tree = _python_tree(text) if file.path.endswith(".py") else None
        if tree is None:
            snippets += [s for s in _around(text, file.path, changed)
                         if not set(range(s.start, s.end + 1)) <= shown_lines(file)]
            continue
        blocks = _enclosing(tree, text, file.path, changed)
        shown = shown_lines(file)
        snippets += [b for b in blocks if not set(range(b.start, b.end + 1)) <= shown]  # not already in the diff
        used = _names_used(file, blocks)
        definitions = _top_level_definitions(tree)
        imports = {alias.asname or alias.name: (alias.name, node.module or "", node.level)
                   for node in tree.body if isinstance(node, ast.ImportFrom) for alias in node.names}
        for name in used:  # in order of importance
            node = definitions.get(name)
            if node and not any(b.start <= node.lineno <= b.end for b in blocks):
                definition = _definition(node, name, text, file.path)
                if not set(range(definition.start, definition.end + 1)) <= shown:
                    later.append(definition)
            elif name in imports:
                imported.append((file.path, *imports[name]))
    snippets += later

    if imported:
        repo_paths = set(await source.paths())
        texts: Dict[str, Optional[str]] = {}
        for importer, name, module, level in imported:
            for path in _module_paths(module, level, importer, repo_paths):
                if path not in texts:
                    if len(texts) >= MAX_IMPORTED_FILES:
                        continue
                    texts[path] = await source.read(path)
                tree = _python_tree(texts[path] or "")
                node = _top_level_definitions(tree).get(name) if tree else None
                if node:
                    snippets.append(_definition(node, name, texts[path], path))
                    break

    parts, used_tokens, seen = [], 0, set()
    for snippet in snippets:
        if (snippet.path, snippet.start, snippet.end) in seen:
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
    return ("### Context: unchanged code from the repository, for reference (not part of the change; "
            "don't comment on it)\n\n" + "\n\n".join(parts))
