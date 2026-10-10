"""Python, read with the standard library's ast (see codemop.review.code)."""
import ast
import builtins
import functools
import keyword
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from codemop.review.code import Block, searchable

_BLOCKS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _block(node: ast.stmt, name: str) -> Block:
    kind = "class" if isinstance(node, ast.ClassDef) else "def"
    return Block(node.lineno, node.end_lineno or node.lineno, kind, name)


class PythonCode:
    def __init__(self, tree: ast.Module):
        self.tree = tree

    def innermost(self, line: int) -> Optional[Block]:
        around = [n for n in ast.walk(self.tree)
                  if isinstance(n, _BLOCKS) and n.lineno <= line <= (n.end_lineno or n.lineno)]
        node = min(around, key=lambda b: (b.end_lineno or b.lineno) - b.lineno, default=None)
        return _block(node, node.name) if node else None

    def changed_definitions(self, changed: Set[int]) -> Dict[str, str]:
        def owner(line: int) -> Optional[str]:
            top = next((n for n in self.tree.body if n.lineno <= line <= (n.end_lineno or n.lineno)), None)
            return top.name if isinstance(top, _BLOCKS) else None

        names = {block.name: owner(block.start) or block.name
                 for block in (self.innermost(line) for line in sorted(changed)) if block}
        bodies = [self.tree.body] + [node.body for node in self.tree.body if isinstance(node, ast.ClassDef)]
        for node in (node for body in bodies for node in body):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
                    node.lineno <= line <= (node.end_lineno or node.lineno) for line in changed):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names.update((t.id, owner(node.lineno) or t.id) for t in targets if isinstance(t, ast.Name))
        return {name: names[name] for name in searchable(list(names), PYTHON.ignored)}

    def top_level_definitions(self) -> Dict[str, Block]:
        definitions = {}
        for node in self.tree.body:
            if isinstance(node, _BLOCKS):
                definitions[node.name] = _block(node, node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        definitions[target.id] = Block(node.lineno, node.end_lineno or node.lineno, "defines",
                                                       target.id)
        return definitions

    def imports(self) -> Dict[str, Tuple[str, object]]:
        return {alias.asname or alias.name: (alias.name, (node.module or "", node.level))
                for node in self.tree.body if isinstance(node, ast.ImportFrom) for alias in node.names}

    def imported_from(self, module: str) -> Set[str]:
        found = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[-1] == module:
                    found |= {alias.name for alias in node.names}
                if any(alias.name == module for alias in node.names):
                    found.add("*")
            elif isinstance(node, ast.Import) and any(alias.name.split(".")[-1] == module for alias in node.names):
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
        tree = _parse(text)
        return PythonCode(tree) if tree else None

    def module_name(self, path: str) -> str:
        file = Path(path)
        return file.parent.name if file.name == "__init__.py" else file.stem

    def module_paths(self, source: object, importer: str, repo_paths: Set[str]) -> List[str]:
        """For `from module import ...` (`source`: the module, and how many levels up it's relative to)"""
        module, level = source
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


@functools.lru_cache(maxsize=512)  # files are read again for each chunk of a diff, and for several names
def _parse(text: str) -> Optional[ast.Module]:
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


PYTHON = Python()
