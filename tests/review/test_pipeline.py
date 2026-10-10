"""
The whole review of a diff, with a fake model.
"""
import pytest

from codemop.providers.base import NoReview, Usage
from codemop.review.chunks import estimate_tokens
from codemop.review.diff import parse_diff
from codemop.review.pipeline import review_diff
from codemop.review.prompt import SYSTEM_PROMPT, render_file, render_hunks
from codemop.review.schema import ModelReview, ModelSuggestion
from review_support import Files


def suggestion(file_path, line, confidence=0.9, title="Issue"):
    return ModelSuggestion(file_path=file_path, line=line, severity="bug", title=title,
                           explanation="e", suggested_code=None, confidence=confidence)


class FakeModel:
    """Answers each chunk by looking up the first file it mentions"""
    name = "fake/model"
    chunk_tokens = 40_000

    def cost(self, usage):
        return usage.input_tokens * 10 / 1_000_000  # $10 per million input tokens

    def __init__(self, answers):
        self.answers = answers  # path -> list of suggestions, or a NoReview to raise
        self.calls = []

    async def review(self, instructions, diff_text):
        self.calls.append((instructions, diff_text))
        path = diff_text.split("\n", 1)[0].removeprefix("### ").rsplit(" (", 1)[0]
        answer = self.answers.get(path, [])
        if isinstance(answer, NoReview):
            raise answer
        return ModelReview(suggestions=answer), Usage(input_tokens=100, output_tokens=10)


@pytest.mark.asyncio
async def test_reviews_reviewable_files_and_reports_the_rest(sample_diff):
    model = FakeModel({"app/service.py": [suggestion("app/service.py", 13), suggestion("app/service.py", 30)]})

    report = await review_diff(sample_diff, model)

    assert report.model == "fake/model"
    assert [(s.file_path, s.line) for s in report.suggestions] == [("app/service.py", 13)]
    assert [(u.suggestion.line, u.reason) for u in report.unplaced] == [
        (30, "lines aren't added or unchanged lines in the diff")
    ]
    assert {s.path for s in report.skipped} == {"old.txt", "docs/b.md", "logo.png", "uv.lock"}
    assert report.complete
    assert model.calls[0][0] == SYSTEM_PROMPT
    assert report.usage == Usage(input_tokens=100, output_tokens=10)  # one chunk


@pytest.mark.asyncio
async def test_suggestions_must_be_for_files_in_their_own_chunk(sample_diff):
    """A model can only point at files it was shown"""
    files = parse_diff(sample_diff)
    service = next(f for f in files if f.path == "app/service.py")
    model = FakeModel({"app/service.py": [suggestion("app/new_module.py", 1)]})

    report = await review_diff(sample_diff, model, chunk_tokens=estimate_tokens(render_file(service)))

    assert report.chunks == 2
    assert report.suggestions == []
    assert [u.reason for u in report.unplaced] == ["file isn't in the reviewed diff"]


@pytest.mark.asyncio
async def test_suggestions_must_be_on_hunks_in_their_own_chunk(sample_diff):
    """When a file is split across chunks, a model can only point at the hunks it was shown"""
    files = parse_diff(sample_diff)
    service = next(f for f in files if f.path == "app/service.py")
    largest_hunk = max(estimate_tokens(render_hunks(service, [h])) for h in service.hunks)

    class AnswersEveryChunk(FakeModel):
        async def review(self, instructions, diff_text):
            self.calls.append((instructions, diff_text))
            # Line 13 is in the first hunk and line 43 in the second, whichever chunk this is
            return ModelReview(suggestions=[suggestion("app/service.py", 13), suggestion("app/service.py", 43)]), Usage()

    report = await review_diff(sample_diff, AnswersEveryChunk({}), chunk_tokens=largest_hunk)

    assert report.chunks == 2  # one of service.py's hunks each (new_module.py fits in the second)
    assert sorted(s.line for s in report.suggestions) == [13, 43]  # each placed once, from its own chunk
    assert sorted(u.suggestion.line for u in report.unplaced) == [13, 43]  # and set aside from the other


@pytest.mark.asyncio
async def test_low_confidence_suggestions_are_counted_not_kept(sample_diff):
    model = FakeModel({"app/service.py": [suggestion("app/service.py", 12, 0.3), suggestion("app/service.py", 13, 0.8)]})

    report = await review_diff(sample_diff, model, min_confidence=0.5)

    assert [s.line for s in report.suggestions] == [13]
    assert report.below_confidence == 1


@pytest.mark.asyncio
async def test_a_failed_chunk_is_reported_and_the_rest_still_reviewed(sample_diff):
    files = parse_diff(sample_diff)
    service = next(f for f in files if f.path == "app/service.py")
    model = FakeModel({
        "app/service.py": NoReview.refused("fake/model", Usage(input_tokens=50)),
        "app/new_module.py": [suggestion("app/new_module.py", 2)],
    })

    report = await review_diff(sample_diff, model, chunk_tokens=estimate_tokens(render_file(service)))

    assert [(f.paths, f.kind) for f in report.failed] == [(["app/service.py"], "refused")]
    assert [s.file_path for s in report.suggestions] == ["app/new_module.py"]
    assert not report.complete
    assert report.usage.input_tokens == 150


@pytest.mark.asyncio
async def test_a_fatal_error_stops_the_chunks_not_yet_started(sample_diff):
    files = parse_diff(sample_diff)
    service = next(f for f in files if f.path == "app/service.py")
    model = FakeModel({"app/service.py": NoReview("rejected API key", fatal=True)})

    report = await review_diff(sample_diff, model, chunk_tokens=estimate_tokens(render_file(service)), concurrency=1)

    assert report.stopped == "rejected API key"
    assert len(model.calls) == 1
    assert [(f.reason, f.kind) for f in report.failed] == [
        ("rejected API key", "error"), ("not reviewed: rejected API key", "not_reviewed")
    ]


@pytest.mark.asyncio
async def test_empty_diff():
    report = await review_diff("", FakeModel({}))

    assert report.chunks == 0
    assert report.suggestions == [] and report.complete


@pytest.mark.asyncio
async def test_chunk_size_defaults_to_the_models_own(sample_diff):
    files = parse_diff(sample_diff)
    service = next(f for f in files if f.path == "app/service.py")
    model = FakeModel({})
    model.chunk_tokens = estimate_tokens(render_file(service))

    report = await review_diff(sample_diff, model)

    assert report.chunks == 2


@pytest.mark.asyncio
async def test_a_diff_over_the_changed_line_limit_isnt_sent_to_the_model(sample_diff):
    model = FakeModel({})

    report = await review_diff(sample_diff, model, max_changed_lines=5)

    # app/service.py: 2 removed + 3 added; app/new_module.py: 3 added (the lock file is ignored)
    assert report.too_large == "8 changed lines to review, more than the limit of 5"
    assert model.calls == []
    assert not report.complete


@pytest.mark.asyncio
async def test_a_diff_within_the_limit_is_reviewed(sample_diff):
    model = FakeModel({})

    report = await review_diff(sample_diff, model, max_changed_lines=8)

    assert report.too_large is None
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_context_comes_before_the_change(sample_diff):
    # service.py as of the change: the diff shows lines 10-16 of a class that runs from 9 to 40
    service = "\n" * 8 + "class Service:\n" + "".join(f"    x{n} = {n}\n" for n in range(10, 41))

    model = FakeModel({})

    await review_diff(sample_diff, model, context=Files({"app/service.py": service}))

    sent = model.calls[0][1]
    assert sent.startswith("### Context: unchanged code from the repository")
    assert "#### app/service.py, lines 9-40 (class Service)" in sent
    assert "\n\n### The change\n\n### app/service.py (modified)" in sent


@pytest.mark.asyncio
async def test_no_context_section_when_theres_none(sample_diff):
    model = FakeModel({})

    await review_diff(sample_diff, model, context=Files({}))

    assert model.calls[0][1].startswith("### app/service.py (modified)")
