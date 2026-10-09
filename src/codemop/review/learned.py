"""
What CodeMop has been told isn't a problem, so it doesn't raise it again.

Two kinds:
- learned: for the whole repository, kept in .codemop-learned.yml, which `/codemop learn`
  adds to and anyone can edit. Read from the default branch, like .codemop.yml, so a pull
  request can't quietly teach CodeMop to ignore its own bug
- dismissed: for one pull request, the CodeMop comments someone resolved there

Both are given to the model as already settled; dismissed ones are also filtered out, in
case the model raises them anyway (same_issue decides, here and when a re-review matches
new suggestions to earlier findings).
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

import yaml

from codemop.review.schema import ModelSuggestion, Severity

LEARNED_FILE = ".codemop-learned.yml"
MAX_LEARNED = 100  # entries given to the model; a longer file is cut short
MAX_TEXT = 300  # characters of each field
NEAR_LINES = 3  # how close a suggestion must be to an earlier issue to be it again, reworded
SIMILAR_TITLES = 0.5  # and the share of their titles' words in common

HEADER = """\
# What this repository's reviewers have told CodeMop isn't a problem here. CodeMop reads this
# file from the default branch and won't raise these again. Edit or delete entries freely:
# replying `/codemop learn <why>` to a CodeMop comment adds one.
"""


@dataclass(frozen=True)
class Learned:
    path: str  # the file it came up in
    issue: str  # what CodeMop said
    reason: str  # why it's fine here
    source: str = ""  # where it was learned, e.g. "#12, @sam"


@dataclass(frozen=True)
class Dismissed:
    path: str
    line: Optional[int]  # None for a conversation on lines that have since changed
    severity: Severity
    issue: str


def _similar(a: str, b: str) -> bool:
    words_a, words_b = (set(re.findall(r"[a-z0-9_]+", t.lower())) for t in (a, b))
    return bool(words_a and words_b) and len(words_a & words_b) / len(words_a | words_b) >= SIMILAR_TITLES


def same_issue(s: ModelSuggestion, path: str, line: Optional[int], severity: Severity, title: str) -> bool:
    """
    Whether a suggestion is an earlier issue raised again: same file and severity, and the
    same title, or nearby with a similar one (the model rewords its titles). A different
    issue on a nearby line is a new one.
    """
    if s.file_path != path or s.severity != severity:
        return False
    return s.title == title or (line is not None and abs(s.line - line) <= NEAR_LINES and _similar(s.title, title))


def _text(value) -> str:
    return " ".join(str(value or "").split())[:MAX_TEXT]


def parse_learned(text: Optional[str]) -> List[Learned]:
    """The entries in a .codemop-learned.yml; anything malformed is skipped, not fatal"""
    try:
        data = yaml.safe_load(text or "") or []
    except yaml.YAMLError:
        return []
    entries = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("issue") and item.get("reason"):
            entries.append(Learned(_text(item.get("path")), _text(item["issue"]), _text(item["reason"]),
                                   _text(item.get("from"))))
    return entries[:MAX_LEARNED]


def learned_yaml(entry: Learned) -> str:
    """One entry, as it appears in the file"""
    return yaml.safe_dump(
        [{"path": entry.path, "issue": entry.issue, "reason": entry.reason, "from": entry.source}],
        sort_keys=False, allow_unicode=True, width=1000,
    )


def add_learned(text: Optional[str], entry: Learned) -> str:
    """The file with `entry` added at the end (and the explanatory header, if it's new)"""
    existing = (text or HEADER).rstrip("\n") + "\n"
    return existing + "\n" + learned_yaml(entry)


@dataclass(frozen=True)
class Settled:
    learned: Sequence[Learned] = ()
    dismissed: Sequence[Dismissed] = ()

    def instructions(self) -> str:
        """Added to the review instructions: what not to raise again"""
        if not self.learned and not self.dismissed:
            return ""
        lines = ["", "", "These have already been settled by the people reviewing this code. Don't report them "
                         "again, or anything that's the same issue:"]
        lines += [f"- In {e.path}: {e.issue}. It's fine here: {e.reason}" for e in self.learned]
        lines += [f"- In {d.path}" + (f" near line {d.line}" if d.line else "") + f": {d.issue}. Dismissed on "
                  "this pull request" for d in self.dismissed]
        return "\n".join(lines)

    def dismisses(self, s: ModelSuggestion) -> bool:
        """Whether `s` is one of the dismissed issues again"""
        return any(same_issue(s, d.path, d.line, d.severity, d.issue) for d in self.dismissed)
