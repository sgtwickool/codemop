"""
What repository context needs to know about code, for each language it can read: the
function or class around a line, what a change defines, where names are used, and what a file
imports and from where. Python is read with the standard library's ast, TypeScript and
JavaScript with tree-sitter; any other language gets the lines around each change instead.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Sequence, Set, Tuple

MIN_SEARCHED_NAME = 4  # shorter names (id, get, run) are used in too many places to be worth searching for


@dataclass(frozen=True)
class Block:
    """A function, class or other definition: its lines, and what it is"""
    start: int
    end: int
    kind: str  # how it's described, e.g. "def", "class", "function", "interface"
    name: str


class Parsed(Protocol):
    """One file's code, parsed"""

    def innermost(self, line: int) -> Optional[Block]:
        """The innermost named function or class around a line, if it's in one"""

    def changed_definitions(self, changed: Set[int]) -> Dict[str, str]:
        """
        The names the change defines or redefines (functions and classes around the changed
        lines, and what changed top-level or class-level declarations set), each with the
        top-level name a file has to import to use it. Not names too short or common to search for.
        """

    def top_level_definitions(self) -> Dict[str, Block]:
        """What the file defines at its top level, by name"""

    def imports(self) -> Dict[str, Tuple[str, object]]:
        """What the file imports by name: each local name, with its name where it's defined and where from"""

    def imported_from(self, module: str) -> Set[str]:
        """What the file imports from a module (by its module_name): the names, and "*" for the module itself"""

    def references(self, names: Set[str]) -> List[Tuple[int, str]]:
        """Where the code refers to any of `names`: (line, name), in order"""


class Language(Protocol):
    extensions: Tuple[str, ...]
    ignored: Set[str]  # keywords and built-in names, which aren't worth looking up

    def parse(self, path: str, text: str) -> Optional[Parsed]:
        """The file's code, or None if it doesn't parse"""

    def module_name(self, path: str) -> str:
        """The last part of how other files import this one"""

    def module_paths(self, source: object, importer: str, repo_paths: Set[str]) -> List[str]:
        """The repository files an import in `importer` could mean (`source`, as imports() gives it)"""


def language_for(path: str) -> Optional[Language]:
    """The language a file is in, if it's one context can read"""
    from codemop.review.code.python import PYTHON
    from codemop.review.code.typescript import TYPESCRIPT

    suffix = Path(path).suffix
    return next((language for language in (PYTHON, TYPESCRIPT) if suffix in language.extensions), None)


def searchable(names: Sequence[str], ignored: Set[str]) -> List[str]:
    """The names worth looking for elsewhere: not too short, not dunder, not keywords or built-ins"""
    return [name for name in names if len(name) >= MIN_SEARCHED_NAME and not name.startswith("__") and name not in ignored]
