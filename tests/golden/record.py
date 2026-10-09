"""
Records a golden case's model answers: reviews cases/<name>/diff.diff with a real model and
the case's settings.json, and saves each chunk's answer to responses.json. It costs whatever
the model costs (nothing with Ollama). Then write the expected outputs from the recording:

    python tests/golden/record.py <name> --provider ollama --model qwen2.5-coder:7b
    CODEMOP_UPDATE_GOLDEN=1 pytest tests/golden
"""
import argparse
import asyncio
import dataclasses
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from codemop.providers import create_model  # noqa: E402
from codemop.providers.base import NoReview  # noqa: E402
from codemop.review.chunks import DEFAULT_IGNORED_PATHS  # noqa: E402
from codemop.review.pipeline import review_diff  # noqa: E402
from test_golden import CASES, chunk_key  # noqa: E402


class Recording:
    """Passes each chunk to the real model and keeps its answer"""

    def __init__(self, model):
        self.model = model
        self.name = model.name
        self.chunk_tokens = model.chunk_tokens
        self.chunks = []

    def cost(self, usage):
        return self.model.cost(usage)

    async def review(self, instructions, diff_text):
        try:
            review, usage = await self.model.review(instructions, diff_text)
        except NoReview as e:
            self.chunks.append({"key": chunk_key(diff_text), "no_review": e.reason, "fatal": e.fatal,
                                "usage": dataclasses.asdict(e.usage)})
            raise
        self.chunks.append({"key": chunk_key(diff_text), "review": review.model_dump(mode="json"),
                            "usage": dataclasses.asdict(usage)})
        return review, usage


async def record(case: Path, provider: str, model_name: str) -> None:
    settings = json.loads((case / "settings.json").read_text())
    recording = Recording(create_model(provider, model_name))
    report = await review_diff(
        (case / "diff.diff").read_text(), recording,
        chunk_tokens=settings.get("chunk_tokens"),
        min_confidence=settings.get("min_confidence", 0.5),
        ignored_paths=[*DEFAULT_IGNORED_PATHS, *settings.get("ignore", [])],
        concurrency=1,
    )
    (case / "responses.json").write_text(json.dumps({
        "model": recording.name,
        "chunk_tokens": recording.chunk_tokens,
        "recorded": datetime.date.today().isoformat(),
        "chunks": recording.chunks,
    }, indent=2) + "\n")
    print(f"recorded {len(recording.chunks)} chunk(s) from {recording.name}: "
          f"{len(report.suggestions)} suggestion(s), {len(report.unplaced)} set aside")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case", help="a folder name in tests/golden/cases/")
    parser.add_argument("--provider", default="anthropic")
    parser.add_argument("--model")
    args = parser.parse_args()
    asyncio.run(record(CASES / args.case, args.provider, args.model))


if __name__ == "__main__":
    main()
