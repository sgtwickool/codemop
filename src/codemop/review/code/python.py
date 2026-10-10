"""Python, read with the standard library's ast (see codemop.review.code)."""
import ast
import builtins
import functools
import keyword
from pathlib import Path
from typing import Dict, Hashable, List, Optional, Set, Tuple

from codemop.review.code.base import Block, Import, owners, paths_ending_with, searchable, touches

_BLOCKS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _end(node: ast.AST) -> int:
    return node.end_lineno or node.lineno


def _block(node: ast.stmt) -> Block:
    return Block(node.lineno, _end(node), "class" if isinstance(node, ast.ClassDef) else "def", node.name)


def _assigned_names(node: ast.stmt) -> List[str]:
    """The plain names an assignment sets (none, if it isn't one)"""
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return []
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name)]


class PythonCode:
    def __init__(self, tree: ast.Module):
        self.tree = tree

    @functools.cached_property
    def _blocks(self) -> List[Block]:
        return [_block(node) for node in ast.walk(self.tree) if isinstance(node, _BLOCKS)]

    @functools.cached_property
    def _definitions(self) -> Dict[str, Block]:
        definitions = {}
        for node in self.tree.body:
            if isinstance(node, _BLOCKS):
                definitions[node.name] = _block(node)
            for name in _assigned_names(node):
                definitions[name] = Block(node.lineno, _end(node), "defines", name)
        return definitions

    @functools.cached_property
    def _imports(self) -> List[ast.stmt]:
        return [node for node in ast.walk(self.tree) if isinstance(node, (ast.Import, ast.ImportFrom))]

    def innermost(self, line: int) -> Optional[Block]:
        return min((b for b in self._blocks if b.covers(line)), key=lambda b: b.end - b.start, default=None)

    def changed_definitions(self, changed: Set[int]) -> Dict[str, Set[str]]:
        names: Dict[str, Set[str]] = {}

        def add(name: str, line: int) -> None:
            names.setdefault(name, set()).update(owners(self._definitions, line) or {name})

        for block in filter(None, map(self.innermost, sorted(changed))):
            add(block.name, block.start)
        bodies = [self.tree.body] + [node.body for node in self.tree.body if isinstance(node, ast.ClassDef)]
        for node in (node for body in bodies for node in body):
            if touches(node.lineno, _end(node), changed):
                for name in _assigned_names(node):
                    add(name, node.lineno)
        return searchable(names, PYTHON.ignored)

    def top_level_definitions(self) -> Dict[str, Block]:
        return self._definitions

    def imports(self) -> Dict[str, Import]:
        return {alias.asname or alias.name: Import(alias.name, (node.module or "", node.level))
                for node in self.tree.body if isinstance(node, ast.ImportFrom) for alias in node.names}

    def imported_from(self, module: str) -> Set[str]:
        found = set()
        for node in self._imports:
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[-1] == module:
                    found |= {alias.name for alias in node.names}
                if any(alias.name == module for alias in node.names):
                    found.add("*")
            elif any(alias.name.split(".")[-1] == module for alias in node.names):
                found.add("*")
        return found

    def references(self, names: Set[str]) -> List[Tuple[int, str]]:
        """As a name, an attribute or a keyword argument"""
        found = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.keyword):
                name = node.arg
            else:
                continue
            if name in names:
                found.append((node.lineno, name))
        return sorted(found)


class Python:
    extensions = (".py",)
    ignored = set(keyword.kwlist) | set(dir(builtins)) | {"self", "cls"}

    def parse(self, path: str, text: str) -> Optional[PythonCode]:
        return _parse(text)

    def module_name(self, path: str) -> str:
        file = Path(path)
        return file.parent.name if file.name == "__init__.py" else file.stem

    def module_paths(self, source: Hashable, importer: str, repo_paths: Set[str]) -> List[str]:
        """For `from module import ...` (`source`: the module, and how many levels up it's relative to)"""
        module, level = source
        if level:  # relative: from the importing file's package
            base = Path(importer).parent
            for _ in range(level - 1):
                base = base.parent
            stem = str(base / module.replace(".", "/")) if module else str(base)
            candidates = [f"{stem}.py".removeprefix("./"), f"{stem}/__init__.py".removeprefix("./")]
            return [c for c in candidates if c in repo_paths]
        tail = module.replace(".", "/")
        return paths_ending_with(repo_paths, (f"{tail}.py", f"{tail}/__init__.py"))


@functools.lru_cache(maxsize=512)  # files are read again for each chunk of a diff, and for several names
def _parse(text: str) -> Optional[PythonCode]:
    try:
        return PythonCode(ast.parse(text))
    except (SyntaxError, ValueError):
        return None


PYTHON = Python()
