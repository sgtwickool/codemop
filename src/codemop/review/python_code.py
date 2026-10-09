"""
What the standard library's ast can tell about Python code, for repository context: the
function around a line, what a change defines, where names are used, and what's imported.
"""
import ast
import builtins
import functools
import keyword
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

BLOCKS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
IGNORED_NAMES = set(keyword.kwlist) | set(dir(builtins)) | {"self", "cls"}
MIN_SEARCHED_NAME = 4  # shorter names (id, get, run) are used in too many places to be worth it


@functools.lru_cache(maxsize=64)  # an imported module is often read by several chunks, for several names
def python_tree(text: str) -> Optional[ast.Module]:
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


def innermost(tree: ast.Module, line: int) -> Optional[ast.stmt]:
    """The innermost function or class around a line, if it's in one"""
    around = [n for n in ast.walk(tree) if isinstance(n, BLOCKS) and n.lineno <= line <= (n.end_lineno or n.lineno)]
    return min(around, key=lambda b: (b.end_lineno or b.lineno) - b.lineno, default=None)


def changed_definitions(tree: ast.Module, changed: Set[int]) -> Dict[str, str]:
    """
    The names the change defines or redefines: the innermost function or class around each
    changed line, and what changed assignments at the top level or in a class body set (a
    constant, a model's field). Each with the top-level name it belongs to (a method or a
    field to its class), which a file using it has to import. Not names too short or common
    to search for.
    """
    def owner(line: int) -> Optional[str]:
        top = next((n for n in tree.body if n.lineno <= line <= (n.end_lineno or n.lineno)), None)
        return top.name if isinstance(top, BLOCKS) else None

    names = {block.name: owner(block.lineno) or block.name
             for block in (innermost(tree, line) for line in sorted(changed)) if block}
    bodies = [tree.body] + [node.body for node in tree.body if isinstance(node, ast.ClassDef)]
    for node in (node for body in bodies for node in body):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
                node.lineno <= line <= (node.end_lineno or node.lineno) for line in changed):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update((t.id, owner(node.lineno) or t.id) for t in targets if isinstance(t, ast.Name))
    return {name: top for name, top in names.items()
            if len(name) >= MIN_SEARCHED_NAME and not name.startswith("__") and name not in IGNORED_NAMES}


def module_name(path: str) -> str:
    """How a file is imported, as the last part of its dotted name"""
    file = Path(path)
    return file.parent.name if file.name == "__init__.py" else file.stem


def imported_from(tree: ast.Module, module: str) -> Set[str]:
    """What a file imports from a module (by the last part of its name): the names, and "*" for the module itself"""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[-1] == module:
                found |= {alias.name for alias in node.names}
            if any(alias.name == module for alias in node.names):
                found.add("*")
        elif isinstance(node, ast.Import) and any(alias.name.split(".")[-1] == module for alias in node.names):
            found.add("*")
    return found


def references(tree: ast.Module, names: Set[str]) -> List[Tuple[int, str]]:
    """Where the code refers to any of `names` (as a name, an attribute or a keyword argument): (line, name)"""
    found = []
    for node in ast.walk(tree):
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


def top_level_definitions(tree: ast.Module) -> Dict[str, ast.stmt]:
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


def module_paths(module: str, level: int, importer: str, repo_paths: Set[str]) -> List[str]:
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
