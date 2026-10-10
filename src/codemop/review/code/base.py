"""What each language's reader provides (see codemop.review.code), and what they share."""
from dataclasses import dataclass
from typing import Dict, Hashable, Iterable, List, NamedTuple, Optional, Protocol, Set, Tuple

MIN_SEARCHED_NAME = 4  # shorter names (id, get, run) are used in too many places to be worth searching for


@dataclass(frozen=True)
class Block:
    """A function, class or other definition: its lines, and what it is"""
    start: int
    end: int
    kind: str  # how it's described, e.g. "def", "class", "function", "interface"
    name: str

    def covers(self, line: int) -> bool:
        return self.start <= line <= self.end


class Import(NamedTuple):
    name: str  # its name where it's defined: "default" for a default export, "*" for the module itself
    source: Hashable  # where from, as the language's module_paths understands it


class Parsed(Protocol):
    """One file's code, parsed"""

    def innermost(self, line: int) -> Optional[Block]:
        """The innermost named function or class around a line, if it's in one"""

    def changed_definitions(self, changed: Set[int]) -> Dict[str, Set[str]]:
        """
        The names the change defines or redefines (functions and classes around the changed
        lines, and what changed top-level or class-level declarations set), each with the names
        a file can import to use it (its class's, for a method). Not names too short or common
        to search for.
        """

    def top_level_definitions(self) -> Dict[str, Block]:
        """What the file defines at its top level, by name (and as "default", if it's the default export)"""

    def imports(self) -> Dict[str, Import]:
        """What the file imports by name, by the name it has here"""

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

    def module_paths(self, source: Hashable, importer: str, repo_paths: Set[str]) -> List[str]:
        """The repository files an import in `importer` could mean"""


def touches(start: int, end: int, lines: Iterable[int]) -> bool:
    return any(start <= line <= end for line in lines)


def owners(definitions: Dict[str, Block], line: int) -> Set[str]:
    """The top-level names a line belongs to (one declaration can be exported by name and as default)"""
    return {name for name, block in definitions.items() if block.covers(line)}


def searchable(names: Dict[str, Set[str]], ignored: Set[str]) -> Dict[str, Set[str]]:
    """The names worth looking for elsewhere: not too short, not dunder, not keywords or built-ins"""
    return {name: imported for name, imported in names.items()
            if len(name) >= MIN_SEARCHED_NAME and not name.startswith("__") and name not in ignored}


def paths_ending_with(repo_paths: Set[str], tails: Iterable[str]) -> List[str]:
    """The repository paths that are one of `tails`, or end with one, as a whole path segment"""
    tails = list(tails)
    return sorted(p for p in repo_paths if any(p == tail or p.endswith("/" + tail) for tail in tails))
