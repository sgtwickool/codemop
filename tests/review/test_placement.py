import pytest

from codemop.review.diff import parse_diff
from codemop.review.placement import place_suggestions
from codemop.review.schema import ModelSuggestion


def suggestion(file_path="app/service.py", line=12, end_line=None):
    return ModelSuggestion(
        file_path=file_path, line=line, end_line=end_line, severity="bug",
        title="t", explanation="e", suggested_code=None, confidence=0.9,
    )


@pytest.fixture
def files(sample_diff):
    return parse_diff(sample_diff)


def test_suggestions_on_added_or_unchanged_lines_are_placed(files):
    result = place_suggestions([suggestion(line=12), suggestion(line=10), suggestion(line=12, end_line=13)], files)

    assert len(result.placed) == 3
    assert result.unplaced == []


@pytest.mark.parametrize("bad, reason", [
    (suggestion(file_path="not/in/diff.py"), "file isn't in the reviewed diff"),
    (suggestion(line=30), "lines aren't added or unchanged lines in the diff"),  # between hunks
    (suggestion(line=16, end_line=41), "lines aren't added or unchanged lines in the diff"),  # spans a gap
    (suggestion(line=13, end_line=12), "end_line is before line"),
])
def test_suggestions_elsewhere_are_set_aside_with_a_reason(files, bad, reason):
    result = place_suggestions([bad], files)

    assert result.placed == []
    assert [u.reason for u in result.unplaced] == [reason]
