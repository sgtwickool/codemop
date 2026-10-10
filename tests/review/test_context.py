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
    context = await build_context(parse_diff(DIFF), Files({"app.py": APP, "app/db.py": DB}), budget_tokens=100)

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


ACCOUNTS = '''\
RETRY_DELAY = 2000  # milliseconds


def transfer(source, target, amount):
    source.balance -= amount
    target.balance += amount
'''

# Swaps transfer's arguments, and changes RETRY_DELAY's units: right in itself, wrong for the callers
CALLERS_DIFF = """\
diff --git a/bank/accounts.py b/bank/accounts.py
--- a/bank/accounts.py
+++ b/bank/accounts.py
@@ -1,6 +1,6 @@
-RETRY_DELAY = 2  # seconds
+RETRY_DELAY = 2000  # milliseconds
 
 
-def transfer(amount, source, target):
+def transfer(source, target, amount):
     source.balance -= amount
     target.balance += amount
"""

PAYMENTS = '''\
import time

from bank.accounts import RETRY_DELAY, transfer


def pay(invoice, customer, shop):
    """Pay an invoice"""
    transfer(invoice.total, customer, shop)
    invoice.paid = True


def with_retries(action):
    for _ in range(3):
        try:
            return action()
        except ConnectionError:
            time.sleep(RETRY_DELAY)
'''

TEST_PAYMENTS = '''\
from bank.accounts import transfer


def test_transfer(a, b):
    transfer(a, b, 5)
'''


@pytest.mark.asyncio
async def test_where_the_changed_definitions_are_used_in_other_files():
    files = Files({"bank/accounts.py": ACCOUNTS, "shop/payments.py": PAYMENTS, "tests/test_payments.py": TEST_PAYMENTS,
                   "shop/unrelated.py": "def other():\n    return 1\n"})

    context = await build_context(parse_diff(CALLERS_DIFF), files)

    uses = [part.split("\n")[0] for part in context.split("\n\n#### ")[1:]]
    assert uses == [
        "shop/payments.py, lines 6-9 (uses transfer)",
        "shop/payments.py, lines 12-17 (uses RETRY_DELAY)",
        "tests/test_payments.py, lines 4-5 (uses transfer)",  # tests after the code
    ]
    assert "transfer(invoice.total, customer, shop)" in context and "time.sleep(RETRY_DELAY)" in context
    assert "def other" not in context


@pytest.mark.asyncio
async def test_a_changed_field_is_found_where_its_set_and_short_names_arent_searched_for():
    model = "class PullRequest:\n    number = Column(Integer, unique=True)\n    id = Column(Integer)\n"
    diff = ("diff --git a/db.py b/db.py\n--- a/db.py\n+++ b/db.py\n@@ -1,2 +1,3 @@\n class PullRequest:\n"
            "+    number = Column(Integer, unique=True)\n     id = Column(Integer)\n")
    store = "from db import PullRequest\n\n\ndef save(event):\n    return PullRequest(number=event['number'], id=event['id'])\n"

    context = await build_context(parse_diff(diff), Files({"db.py": model, "store.py": store}))

    # The field is directly in the class, so the class counts as changed too
    assert "#### store.py, lines 4-5 (uses PullRequest)\n  4 | def save(event):\n  5 |     return PullRequest(number=" in context
    assert context.count("####") == 1 and "(uses id)" not in context


@pytest.mark.asyncio
async def test_uses_are_shown_once_and_at_most_a_few_per_name():
    callers = "\n\n".join(f"def caller_{n}(a, b):\n    transfer(a, b, {n})\n    transfer(b, a, {n})" for n in range(6))
    files = Files({"bank/accounts.py": ACCOUNTS, "shop/many.py": "from bank.accounts import transfer\n\n\n" + callers})

    context = await build_context(parse_diff(CALLERS_DIFF), files)

    assert context.count("(uses transfer)") == 3


@pytest.mark.asyncio
async def test_only_files_that_import_the_changed_code_count_as_using_it():
    """A method or field name like `total` is used all over; only the class's users matter"""
    cart = "class Cart:\n    def total(self):\n        return sum(self.prices)\n"
    diff = ("diff --git a/shop/cart.py b/shop/cart.py\n--- a/shop/cart.py\n+++ b/shop/cart.py\n@@ -1,3 +1,3 @@\n"
            " class Cart:\n     def total(self):\n-        return sum(self.prices)\n+        return round(sum(self.prices), 2)\n")
    files = Files({
        "shop/cart.py": cart.replace("sum(self.prices)", "round(sum(self.prices), 2)"),
        "shop/checkout.py": "from shop.cart import Cart\n\n\ndef pay(cart: Cart):\n    return charge(cart.total())\n",
        "shop/views.py": "from shop import cart\n\n\ndef show(c):\n    return c.total()\n",  # the module
        "stats/sums.py": "def report(rows):\n    return rows.total()\n",  # some other total
    })

    context = await build_context(parse_diff(diff), files)

    assert "shop/checkout.py, lines 4-5 (uses total)" in context and "shop/views.py, lines 4-5 (uses total)" in context
    assert "stats/sums.py" not in context


@pytest.mark.asyncio
async def test_local_files_skip_hidden_and_installed_folders(tmp_path):
    for path in ["app/main.py", "app/notes.txt", ".venv/lib/x.py", "node_modules/y.py", "venv/z.py", "tests/test_a.py"]:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("x = 1\n")

    assert await LocalFiles(tmp_path).paths() == ["app/main.py", "tests/test_a.py"]


@pytest.mark.asyncio
async def test_code_the_diff_shows_isnt_sent_again_as_context_even_from_another_file():
    """Seen in the eval: CORS settings added in one file came back, as "unchanged" context, as
    a definition another file imports, and the model stopped reporting the bug in them"""
    settings = "CORS = {\n    \"allow_origins\": [\"*\"],\n    \"allow_credentials\": True,\n}\n"
    main = "from settings import CORS\n\n\ndef make_app(app):\n    app.add(**CORS)\n    return app\n"
    diff = ("diff --git a/settings.py b/settings.py\nnew file mode 100644\n--- /dev/null\n+++ b/settings.py\n"
            "@@ -0,0 +1,4 @@\n" + "".join(f"+{line}\n" for line in settings.splitlines()) +
            "diff --git a/main.py b/main.py\n--- a/main.py\n+++ b/main.py\n@@ -4,3 +4,3 @@\n def make_app(app):\n"
            "-    app.add()\n+    app.add(**CORS)\n     return app\n")
    files = Files({"settings.py": settings, "main.py": main})
    main_only = [f for f in parse_diff(diff) if f.path == "main.py"]  # main.py's chunk

    in_diff = {f.path: f.commentable_lines() for f in parse_diff(diff)}
    context = await build_context(main_only, files, in_diff=in_diff)

    assert "settings.py" not in context
    assert "defines CORS" in await build_context(main_only, files)  # what happened without the whole diff
