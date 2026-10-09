"""The CLI tests' fakes: a hermetic setup, a fake model, and a fake GitHub (see the github fixture)."""

import pytest

from codemop import providers
from codemop.github import api
from codemop.github.api import GitHubError, IssueComment, PullRequest
from cli_support import (  # noqa: F401
    DIFF, SUGGESTION, FakeModel, run, RecordingModel, TWO_FILE_DIFF, summary_of, tick_all, _async, codemop_comment, learn_reply, posted_with_a_personal_token, new_commit, NEWER, merge_check_on,
)


@pytest.fixture(autouse=True)
def no_repo_config(monkeypatch, tmp_path):
    """
    Repositories have no .codemop.yml unless a test says so, and nothing reaches GitHub. Runs
    in an empty folder, so a local diff's context isn't read from this repository's own files.
    """
    files = {}
    monkeypatch.chdir(tmp_path)

    async def fake_fetch_repo_file(repo, path, ref=None, token=None, api_url=None):
        return files.get((repo, path))

    async def no_threads(pr, token=None, api_url=None):
        return []

    async def an_open_pr(pr, token=None, api_url=None):
        return PullRequest(head_sha="abc1234" + "0" * 33, state="open", draft=False, head_ref="feature",
                           head_repo=pr.repo)

    async def no_paths(repo, ref, token=None, api_url=None):
        return []
    monkeypatch.setattr(api, "fetch_repo_file", fake_fetch_repo_file)
    monkeypatch.setattr(api, "list_review_threads", no_threads)
    monkeypatch.setattr(api, "fetch_pull_request", an_open_pr)
    async def no_snapshot(repo, ref, token=None, api_url=None):
        return None
    monkeypatch.setattr(api, "list_paths", no_paths)
    monkeypatch.setattr(api, "fetch_snapshot", no_snapshot)
    return files


@pytest.fixture
def fake_model(monkeypatch):
    def use(result):
        monkeypatch.setattr(providers, "create_model", lambda *a, **k: FakeModel(result))
    return use


@pytest.fixture
def pr_diff(monkeypatch):
    async def fake_fetch(pr, token=None, api_url=None):
        return TWO_FILE_DIFF
    monkeypatch.setattr(api, "fetch_pr_diff", fake_fetch)
    monkeypatch.setenv("GITHUB_TOKEN", "x")


@pytest.fixture
def github(monkeypatch):
    """
    A fake GitHub for --post: one open PR at commit abc..., the reviews posted to it, and its
    conversation comments (by id)
    """
    state = {
        "head": "abc1234" + "0" * 33, "head_repo": "owner/repo", "reviews": [], "comments": {}, "reject_inline": False,
        "files": {"app.py": "def total(items):\n    result = sum(items)\n    return result + 1\n"},
        "commits": [], "permissions": {"maintainer": "write", "visitor": "read"}, "branch_moves": 0,
        "while_committing": None,  # something to happen to the PR while fixes are being committed
        "default_branch": {},  # files on the default branch (the PR's are in "files")
        "threads": [], "review_comments": {}, "replies": [], "resolved": [],
        "newer_diff": None,  # what's changed since the last review, if it's an ancestor of the head
        "statuses": [],  # (sha, state, description, target_url) for each merge check status set
        "reactions": [],
    }

    async def fetch_pull_request(pr, token=None, api_url=None):
        return PullRequest(head_sha=state["head"], state="open", draft=False, head_ref="feature",
                           head_repo=state["head_repo"])

    async def fetch_repo_file(repo, path, ref=None, token=None, api_url=None):
        return state["files"].get(path) if ref else state["default_branch"].get(path)

    async def list_review_threads(pr, token=None, api_url=None):
        return list(state["threads"])

    async def compare_commits(repo, base, head, token=None, api_url=None):
        return state["newer_diff"]

    async def set_commit_status(repo, sha, status, description, target_url=None, token=None, api_url=None):
        state["statuses"].append((sha, status, description, target_url))

    async def react_to_issue_comment(repo, comment_id, reaction, token=None, api_url=None):
        state["reactions"].append((comment_id, reaction))

    async def fetch_review_comment(repo, comment_id, token=None, api_url=None):
        return state["review_comments"].get(comment_id)

    async def reply_to_review_comment(pr, comment_id, body, token=None, api_url=None):
        state["replies"].append((comment_id, body))
        return "https://github.com/reply"

    async def resolve_thread(thread_id, token=None, api_url=None):
        state["resolved"].append(thread_id)

    async def user_permission(repo, user, token=None, api_url=None):
        return state["permissions"].get(user, "none")

    async def commit_files(repo, branch, parent_sha, files, message, token=None, api_url=None):
        if state["branch_moves"]:
            state["branch_moves"] -= 1
            state["head"] = "moved00" + "0" * 33
            raise GitHubError("the branch moved", 422)
        assert (repo, branch, parent_sha) == (state["head_repo"], "feature", state["head"])
        if state["while_committing"]:
            state["while_committing"]()
        state["files"].update(files)
        state["commits"].append(message)
        state["head"] = "c0ffee0" + "0" * 33
        return state["head"]

    async def list_issue_comments(pr, token=None, api_url=None):
        return [IssueComment(id=i, body=body, author=author, author_is_bot=author.endswith("[bot]"),
                             author_association=association)
                for i, (body, author, association) in state["comments"].items()]

    async def fetch_pr_diff(pr, token=None, api_url=None):
        return DIFF

    async def post_review(pr, review, token=None, api_url=None):
        if state["reject_inline"]:
            raise GitHubError("GitHub rejected the review", 422)
        state["reviews"].append(review)
        return f"https://github.com/owner/repo/pull/7#pullrequestreview-{len(state['reviews'])}"

    async def post_issue_comment(pr, body, comment_id=None, token=None, api_url=None):
        comment_id = comment_id or len(state["comments"]) + 100
        state["comments"][comment_id] = (body, "github-actions[bot]", "NONE")
        return f"https://github.com/owner/repo/pull/7#issuecomment-{comment_id}"

    for name, fake in [("fetch_pull_request", fetch_pull_request), ("list_issue_comments", list_issue_comments),
                       ("fetch_pr_diff", fetch_pr_diff), ("post_review", post_review),
                       ("post_issue_comment", post_issue_comment), ("fetch_repo_file", fetch_repo_file),
                       ("user_permission", user_permission), ("commit_files", commit_files),
                       ("list_review_threads", list_review_threads), ("fetch_review_comment", fetch_review_comment),
                       ("reply_to_review_comment", reply_to_review_comment), ("resolve_thread", resolve_thread),
                       ("compare_commits", compare_commits), ("set_commit_status", set_commit_status),
                       ("react_to_issue_comment", react_to_issue_comment)]:
        monkeypatch.setattr(api, name, fake)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    return state
