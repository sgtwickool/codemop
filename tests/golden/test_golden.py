"""
Golden tests: real recorded model answers, replayed through the whole review, from the diff to
the printed report, with no network.

Each case in cases/<name>/ has the diff, the settings it's reviewed with, and the model's
recorded answer for each chunk (responses.json, written by record.py). The test checks what
was sent to the model (requests.txt) and the text and JSON reports (report.txt, report.json)
against the saved copies, so any change to parsing, chunking, the prompt, placement or the
output shows up as a diff. When a change is intended, accept it with:

    CODEMOP_UPDATE_GOLDEN=1 pytest tests/golden
"""
import json
import os
from pathlib import Path

import pytest

from codemop.cli.review import report_json, report_text
from codemop.providers.base import NoReview, Usage
from codemop.providers.pricing import ANTHROPIC_PRICES
from codemop.review.chunks import DEFAULT_IGNORED_PATHS
from codemop.review.pipeline import review_diff
from codemop.review.prompt import SYSTEM_PROMPT
from codemop.review.schema import ModelReview

CASES = Path(__file__).parent / "cases"
UPDATE = os.environ.get("CODEMOP_UPDATE_GOLDEN") == "1"


def chunk_key(diff_text: str) -> str:
    """Which part of the diff a chunk covers: its file and hunk headers (stable when the prompt changes)"""
    return "\n".join(line for line in diff_text.splitlines() if line.startswith(("### ", "@@")))


class ReplayModel:
    """Answers each chunk with the model's recorded answer for it"""

    def __init__(self, recorded: dict):
        self.name = recorded["model"]
        self.chunk_tokens = recorded["chunk_tokens"]
        self.answers = {chunk["key"]: chunk for chunk in recorded["chunks"]}
        self.requests = []

    def cost(self, usage: Usage):
        provider, _, model = self.name.partition("/")
        if provider == "ollama":
            return 0.0
        price = ANTHROPIC_PRICES.get(model) if provider == "anthropic" else None
        return price.cost(usage) if price else None

    async def review(self, instructions: str, diff_text: str):
        assert instructions == SYSTEM_PROMPT
        self.requests.append(diff_text)
        answer = self.answers.get(chunk_key(diff_text))
        assert answer, f"no recorded answer for this chunk (chunking changed? re-record):\n{chunk_key(diff_text)}"
        usage = Usage(**answer["usage"])
        if "no_review" in answer:
            raise NoReview(answer["no_review"], fatal=answer.get("fatal", False), usage=usage)
        return ModelReview.model_validate(answer["review"]), usage


def check(path: Path, actual: str) -> None:
    if UPDATE:
        path.write_text(actual)
        return
    assert path.exists(), f"{path} is missing: run with CODEMOP_UPDATE_GOLDEN=1 to write it"
    assert actual == path.read_text(), f"{path.name} changed; if that's intended, run with CODEMOP_UPDATE_GOLDEN=1"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", sorted(p for p in CASES.iterdir() if p.is_dir()), ids=lambda p: p.name)
async def test_golden(case: Path):
    settings = json.loads((case / "settings.json").read_text())
    model = ReplayModel(json.loads((case / "responses.json").read_text()))

    report = await review_diff(
        (case / "diff.diff").read_text(), model,
        chunk_tokens=settings.get("chunk_tokens"),
        min_confidence=settings.get("min_confidence", 0.5),
        ignored_paths=[*DEFAULT_IGNORED_PATHS, *settings.get("ignore", [])],
        concurrency=1,  # chunks in a fixed order, so requests.txt is stable
    )

    target = f"golden/{case.name}"
    check(case / "requests.txt", f"{SYSTEM_PROMPT}\n\n" + "".join(f"===== chunk\n{r}\n" for r in model.requests))
    check(case / "report.txt", report_text(report, target, "defaults") + "\n")
    check(case / "report.json", report_json(report, target, "defaults") + "\n")
