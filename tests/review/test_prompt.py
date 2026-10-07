from codemop.review.diff import parse_diff
from codemop.review.prompt import render_file


def test_lines_show_markers_and_new_line_numbers(sample_diff):
    service = next(f for f in parse_diff(sample_diff) if f.path == "app/service.py")

    rendered = render_file(service).splitlines()

    assert rendered[0] == "### app/service.py (modified)"
    assert rendered[1].startswith("@@ -10,6 +10,7 @@")
    assert rendered[2:7] == [
        "  10 |     def __init__(self, client):",
        "  11 |         self.client = client",
        "-    |         self.cache = {}",
        "+ 12 |         self.cache = None",
        "+ 13 |         self.retries = 3",
    ]


def test_renames_show_the_old_path(sample_diff):
    renamed = next(f for f in parse_diff(sample_diff) if f.path == "docs/b.md")

    assert render_file(renamed) == "### docs/b.md (renamed from docs/a.md)"
