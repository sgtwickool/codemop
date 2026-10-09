"""What the CLI tests share: a diff, a fake model, running the command, and steps of the GitHub flows."""
import io


from codemop import cli
from codemop.github.api import ReviewComment, ReviewThread
from codemop.github.review import review_payload
from codemop.providers.base import Usage
from codemop.review.schema import ModelReview, ModelSuggestion


DIFF = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 def total(items):
-    return sum(items)
+    result = sum(items)
+    return result + 1
"""


SUGGESTION = ModelSuggestion(
    file_path="app.py", line=3, severity="bug", title="Adds one to the total",
    explanation="The +1 changes the result; it looks accidental.", suggested_code="    return result",
    confidence=0.9,
)


class FakeModel:
    name = "fake/model"
    chunk_tokens = 40_000

    def cost(self, usage):
        return usage.input_tokens * 10 / 1_000_000  # $10 per million input tokens

    def __init__(self, result):
        self.result = result

    async def review(self, instructions, diff_text):
        if isinstance(self.result, Exception):
            raise self.result
        return ModelReview(suggestions=self.result), Usage(input_tokens=1234, output_tokens=56)


def run(capsys, monkeypatch, argv, stdin=""):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


class RecordingModel(FakeModel):
    """Remembers what review_diff was asked to do, via the chunks it receives"""
    seen = []

    async def review(self, instructions, diff_text):
        RecordingModel.seen.append(diff_text)
        return await super().review(instructions, diff_text)


TWO_FILE_DIFF = DIFF + """\
diff --git a/docs/guide.md b/docs/guide.md
--- a/docs/guide.md
+++ b/docs/guide.md
@@ -1 +1 @@
-old
+new
"""


def summary_of(github):
    [(body, _, _)] = [c for c in github["comments"].values() if "codemop-summary" in c[0]]
    return body


def tick_all(github):
    [(cid, (body, author, association))] = [(i, c) for i, c in github["comments"].items() if "codemop-summary" in c[0]]
    github["comments"][cid] = (body.replace("- [ ]", "- [x]"), author, association)


async def _async(value):
    return value


def codemop_comment(github, comment_id=500, path="app.py", line=3):
    """One of CodeMop's comments on the code, as posted, in its own thread"""
    body = review_payload([SUGGESTION.model_copy(update={"file_path": path, "line": line})], github["head"])["comments"][0]["body"]
    github["review_comments"][comment_id] = ReviewComment(comment_id, body, path, line, None, "github-actions[bot]", True)
    github["threads"].append(ReviewThread(f"thread-{comment_id}", False, path, line, comment_id, body, True, "NONE"))
    return comment_id


def learn_reply(github, text, author="maintainer", reply_id=501, to=500):
    github["review_comments"][reply_id] = ReviewComment(reply_id, text, "app.py", 3, to, author, False)
    return reply_id


def posted_with_a_personal_token(github, comment_id=500):
    """CodeMop's comment as posted with a maintainer's personal access token: by them, not a bot"""
    old = github["review_comments"][comment_id]
    github["review_comments"][comment_id] = ReviewComment(old.id, old.body, old.path, old.line, None, "maintainer", False, "OWNER")
    github["threads"][0] = ReviewThread(**{**github["threads"][0].__dict__, "first_comment_by_bot": False,
                                           "first_comment_association": "OWNER"})


def new_commit(github, files=None, newer_diff=None):
    github["head"] = "def5678" + "0" * 33
    github["files"].update(files or {})
    github["newer_diff"] = newer_diff


NEWER = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 def total(items):
     result = sum(items)
+    # comment
     return result + 1
"""


def merge_check_on(github):
    github["default_branch"][".codemop.yml"] = "merge_check: true\n"
