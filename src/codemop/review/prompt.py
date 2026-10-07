"""
The instructions given to every model, and how a diff is shown to it.

Each line is shown with its new-file line number, so the model can say exactly which line
an issue is on; those numbers are what GitHub review comments use.
"""
from typing import Iterable

from codemop.review.diff import FileDiff, Hunk

SYSTEM_PROMPT = """\
You are reviewing a pull request. Report real problems in the changed code: bugs, security
issues, performance problems, and code that is hard to maintain in a way that will cause bugs.
Don't report style preferences, naming, formatting or missing comments.

The diff shows each file's changes in hunks. Every line has a marker and a line number:
  "+ 12 | ..." is an added line, number 12 in the new version of the file
  "  12 | ..." is an unchanged line, number 12 in the new version
  "-    | ..." is a removed line; it has no new line number, so never point at it

For each problem:
- file_path is the path exactly as it appears after "###"
- line (and end_line, for several lines) are new-file numbers of added or unchanged lines
  shown in the diff. Prefer pointing at added lines
- suggested_code, if you have a concrete fix, replaces lines line..end_line exactly: the
  complete new code for those lines, with no "+"/"-" markers and no line numbers
- confidence is how sure you are the problem is real

Only report problems you are confident about. If the changes look fine, return no suggestions.\
"""


def render_hunks(file: FileDiff, hunks: Iterable[Hunk]) -> str:
    """A file's hunks with markers and new-file line numbers, as the model sees them"""
    hunks = list(hunks)
    width = max(
        (len(str(line.new_number)) for hunk in hunks for line in hunk.lines if line.new_number),
        default=1,
    )
    title = f"### {file.path} ({file.status}"
    if file.status == "renamed" and file.old_path:
        title += f" from {file.old_path}"
    parts = [title + ")"]
    for hunk in hunks:
        parts.append(hunk.header)
        for line in hunk.lines:
            marker = {"added": "+", "removed": "-", "context": " "}[line.kind]
            number = str(line.new_number).rjust(width) if line.new_number else " " * width
            parts.append(f"{marker} {number} | {line.text}")
    return "\n".join(parts)


def render_file(file: FileDiff) -> str:
    return render_hunks(file, file.hunks)
