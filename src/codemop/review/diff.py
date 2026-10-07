"""
Parsing unified diffs (as GitHub returns them) into files, hunks and lines.

Each line keeps its number in the old and new versions of the file, because GitHub only
accepts review comments on lines that appear in the diff.
"""
import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Set

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")

LineKind = Literal["added", "removed", "context"]
FileStatus = Literal["added", "deleted", "modified", "renamed"]


@dataclass(frozen=True)
class DiffLine:
    kind: LineKind
    text: str
    old_number: Optional[int]  # None for added lines
    new_number: Optional[int]  # None for removed lines


@dataclass
class Hunk:
    header: str  # the whole "@@ -a,b +c,d @@ context" line
    lines: List[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    old_path: Optional[str]  # None for an added file
    new_path: Optional[str]  # None for a deleted file
    status: FileStatus
    hunks: List[Hunk] = field(default_factory=list)
    is_binary: bool = False

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""

    def commentable_lines(self) -> Set[int]:
        """New-file line numbers a review comment can go on: added or unchanged lines shown in the diff"""
        return {
            line.new_number
            for hunk in self.hunks
            for line in hunk.lines
            if line.new_number is not None
        }


def _strip_prefix(path: str, prefix: str) -> Optional[str]:
    if path == "/dev/null":
        return None
    return path[len(prefix):] if path.startswith(prefix) else path


def _paths_from_git_header(line: str) -> tuple[Optional[str], Optional[str]]:
    """Paths from "diff --git a/x b/y", used when there are no ---/+++ lines (renames, binaries)"""
    rest = line[len("diff --git "):]
    split = rest.rfind(" b/")
    if not rest.startswith("a/") or split == -1:
        return None, None
    return rest[2:split], rest[split + 3:]


def parse_diff(diff: str) -> List[FileDiff]:
    """Parse a unified diff, as `git diff` or the GitHub API produce, into files"""
    files: List[FileDiff] = []
    current: Optional[FileDiff] = None
    hunk: Optional[Hunk] = None
    old_number = new_number = 0

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            old_path, new_path = _paths_from_git_header(line)
            current = FileDiff(old_path=old_path, new_path=new_path, status="modified")
            files.append(current)
            hunk = None
            continue
        if current is None:
            continue

        if hunk is None:
            # File header lines, before the first hunk
            if line.startswith("new file mode"):
                current.status, current.old_path = "added", None
            elif line.startswith("deleted file mode"):
                current.status, current.new_path = "deleted", None
            elif line.startswith("rename from "):
                current.status, current.old_path = "renamed", line[len("rename from "):]
            elif line.startswith("rename to "):
                current.new_path = line[len("rename to "):]
            elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
                current.is_binary = True
            elif line.startswith("--- "):
                current.old_path = _strip_prefix(line[4:], "a/")
            elif line.startswith("+++ "):
                current.new_path = _strip_prefix(line[4:], "b/")

        match = HUNK_HEADER.match(line)
        if match:
            old_number, new_number = int(match.group(1)), int(match.group(2))
            hunk = Hunk(header=line)
            current.hunks.append(hunk)
            continue
        if hunk is None or line.startswith("\\"):  # "\ No newline at end of file"
            continue

        if line.startswith("+"):
            hunk.lines.append(DiffLine("added", line[1:], None, new_number))
            new_number += 1
        elif line.startswith("-"):
            hunk.lines.append(DiffLine("removed", line[1:], old_number, None))
            old_number += 1
        else:
            # Context lines start with a space; some tools drop it from empty lines
            hunk.lines.append(DiffLine("context", line[1:], old_number, new_number))
            old_number += 1
            new_number += 1

    return files
