import pytest

from codemop.review.context import LocalFiles, build_context
from codemop.review.diff import parse_diff

DB = '''\
PAGE_SIZE = 50


class Session:
    pass


def get_db():
    """A session for one request"""
    return Session()
'''

APP = '''\
from app.db import get_db

LIMIT = 3


def unrelated():
    return 1


def handler(request):
    db = get_db()
    rows = db.query(request.args)
    if len(rows) > LIMIT:
        rows = rows[:LIMIT]
    return rows
'''

# Changes line 13 of app.py (inside handler), which uses LIMIT and get_db
DIFF = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -11,4 +11,4 @@ def handler(request):
     db = get_db()
     rows = db.query(request.args)
-    if len(rows) >= LIMIT:
+    if len(rows) > LIMIT:
         rows = rows[:LIMIT]
"""


class Files:
    def __init__(self, files):
        self.files = files
        self.read_paths = []

    async def read(self, path):
        self.read_paths.append(path)
        return self.files.get(path)

    async def paths(self):
        return list(self.files)


@pytest.mark.asyncio
async def test_the_whole_changed_function_then_what_it_uses():
    context = await build_context(parse_diff(DIFF), Files({"app.py": APP, "app/db.py": DB}))

    assert context.startswith("### Context: unchanged code from the repository, for reference")
    whole, same_file, imported = context.split("\n\n#### ")[1:4]
    assert whole.startswith("app.py, lines 10-15 (def handler)") and "return rows" in whole
    assert same_file.startswith("app.py, lines 3-3 (defines LIMIT)")
    assert imported.startswith("app/db.py, lines 8-10 (defines get_db)")
    assert "def unrelated" not in context and "PAGE_SIZE" not in context


@pytest.mark.asyncio
async def test_the_budget_keeps_the_most_useful_first():
    context = await build_context(parse_diff(DIFF), Files({"app.py": APP, "app/db.py": DB}), budget_tokens=80)

    assert "def handler" in context and "defines LIMIT" in context
    assert "defines get_db" not in context


@pytest.mark.asyncio
async def test_something_too_big_for_the_budget_doesnt_stop_smaller_things_fitting():
    context = await build_context(parse_diff(DIFF), Files({"app.py": APP, "app/db.py": DB}), budget_tokens=40)

    assert "def handler" not in context
    assert "defines LIMIT" in context


@pytest.mark.asyncio
async def test_other_languages_get_the_lines_around_the_change():
    go = "\n".join(f"line {n}" for n in range(1, 101))
    diff = "diff --git a/main.go b/main.go\n--- a/main.go\n+++ b/main.go\n@@ -50,1 +50,1 @@\n-old\n+line 50\n"

    context = await build_context(parse_diff(diff), Files({"main.go": go}))

    assert "#### main.go, lines 25-75 (around the change)" in context


@pytest.mark.asyncio
async def test_no_context_when_files_cant_be_read_or_dont_parse():
    assert await build_context(parse_diff(DIFF), Files({})) == ""
    broken = await build_context(parse_diff(DIFF), Files({"app.py": "def handler(:\n" * 20}))
    assert "around the change" in broken  # falls back to the lines around it


@pytest.mark.asyncio
async def test_relative_imports_are_followed():
    pkg = APP.replace("from app.db import get_db", "from .db import get_db")
    diff = DIFF.replace("app.py", "pkg/app.py")

    context = await build_context(parse_diff(diff), Files({"pkg/app.py": pkg, "pkg/db.py": DB}))

    assert "pkg/db.py, lines 8-10 (defines get_db)" in context


@pytest.mark.asyncio
async def test_local_files_stay_inside_their_folder(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    files = LocalFiles(tmp_path)

    assert await files.read("app.py") == "x = 1\n"
    assert await files.read("../outside.py") is None
    assert await files.paths() == ["app.py"]


@pytest.mark.asyncio
async def test_nothing_the_diff_already_shows_is_sent_again():
    """A new file's functions are all in the diff already"""
    new_file = "diff --git a/db.py b/db.py\nnew file mode 100644\n--- /dev/null\n+++ b/db.py\n@@ -0,0 +1,10 @@\n" + \
        "".join(f"+{line}\n" for line in DB.splitlines())

    assert await build_context(parse_diff(new_file), Files({"db.py": DB})) == ""
