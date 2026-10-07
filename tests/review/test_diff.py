from codemop.review.diff import parse_diff


def by_path(files):
    return {f.path: f for f in files}


def test_finds_every_file_with_its_status(sample_diff):
    files = by_path(parse_diff(sample_diff))

    assert {path: f.status for path, f in files.items()} == {
        "app/service.py": "modified",
        "app/new_module.py": "added",
        "old.txt": "deleted",
        "docs/b.md": "renamed",
        "logo.png": "modified",
        "uv.lock": "modified",
    }
    assert files["docs/b.md"].old_path == "docs/a.md"
    assert files["app/new_module.py"].old_path is None
    assert files["old.txt"].new_path is None
    assert files["logo.png"].is_binary


def test_hunks_and_line_numbers(sample_diff):
    service = by_path(parse_diff(sample_diff))["app/service.py"]

    assert len(service.hunks) == 2
    first = service.hunks[0].lines
    assert [(l.kind, l.old_number, l.new_number) for l in first[:5]] == [
        ("context", 10, 10),
        ("context", 11, 11),
        ("removed", 12, None),
        ("added", None, 12),
        ("added", None, 13),
    ]
    second = service.hunks[1].lines
    assert [(l.kind, l.new_number, l.text.strip()) for l in second] == [
        ("context", 41, "total = 0"),
        ("context", 42, "for item in items:"),
        ("removed", None, "total += item"),
        ("added", 43, "total += item.value"),
        ("context", 44, "return total"),
    ]


def test_empty_context_lines_and_no_newline_marker(sample_diff):
    service = by_path(parse_diff(sample_diff))["app/service.py"]

    assert service.hunks[0].lines[5].kind == "context"
    assert service.hunks[0].lines[5].text == ""
    assert all(not l.text.startswith("No newline") for h in service.hunks for l in h.lines)


def test_commentable_lines_are_added_and_unchanged_new_lines(sample_diff):
    files = by_path(parse_diff(sample_diff))

    assert files["app/service.py"].commentable_lines() == {10, 11, 12, 13, 14, 15, 16, 41, 42, 43, 44}
    assert files["app/new_module.py"].commentable_lines() == {1, 2, 3}
    assert files["old.txt"].commentable_lines() == set()


def test_removed_lines_that_look_like_headers_stay_lines():
    diff = (
        "diff --git a/q.sql b/q.sql\n--- a/q.sql\n+++ b/q.sql\n"
        "@@ -1,2 +1,1 @@\n--- a comment\n select 1;\n"
    )
    [file] = parse_diff(diff)

    assert [(l.kind, l.text) for l in file.hunks[0].lines] == [("removed", "-- a comment"), ("context", "select 1;")]


def test_empty_diff():
    assert parse_diff("") == []
