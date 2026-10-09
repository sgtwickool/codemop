"""
What CodeMop has been told isn't a problem, so it doesn't raise it again.

Two kinds:
- learned: for the whole repository, kept in .codemop-learned.yml, which `/codemop learn`
  adds to and anyone can edit. Read from the default branch, like .codemop.yml, so a pull
  request can't quietly teach CodeMop to ignore its own bug
- dismissed: for one pull request, the CodeMop comments someone resolved there

Both are given to the model as already settled; dismissed ones are also filtered out by
location, in case the model raises them anyway.
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence

import yaml

from codemop.review.schema import ModelSuggestion, Severity

LEARNED_FILE = ".codemop-learned.yml"
MAX_LEARNED = 100  # entries given to the model; a longer file is cut short
MAX_TEXT = 300  # characters of each field
NEAR_LINES = 3  # a new suggestion this close to a dismissed one, same file and severity, is the same issue

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
    line: Optional[int]
    severity: Optional[Severity]
    issue: str


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
        return any(
            d.path == s.file_path and d.line is not None and abs(d.line - s.line) <= NEAR_LINES
            and d.severity in (None, s.severity)
            for d in self.dismissed
        )
