"""Helpers the commands share: the GitHub token, and the merge check after CodeMop's own changes."""
import os
import shutil
import subprocess  # nosec B404
import sys
from typing import List, Optional, Tuple

from codemop.config import (
    CONFIG_FILE,
    ConfigError,
    RepoConfig,
    parse_config,
)
from codemop.github import api
from codemop.github.api import GitHubError, PullRequestRef, ReviewThread
from codemop.github.check import merge_status
from codemop.github.review import parse_comment
from codemop.github.summary import (
    find_summary,
    read_state,
    record_own_commit,
    sync_threads,
    trusted,
)


def github_token() -> Optional[str]:
    """GITHUB_TOKEN, or the token from a `gh auth login`, so private repos work without setup"""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    gh = shutil.which("gh")
    if token or not gh:
        return token
    # Fixed arguments and no shell, so nothing from the user reaches the command
    result = subprocess.run([gh, "auth", "token"], capture_output=True, text=True)  # nosec B603
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None

WRITE_PERMISSIONS = {"admin", "maintain", "write"}

MAX_COMMENT_CHARS = 65_000  # GitHub's limit is 65,536

def conversations(threads: List[ReviewThread]) -> List[Tuple[str, str, bool]]:
    """(path, title, resolved) for each of the threads CodeMop started"""
    found = []
    for t in threads:
        parsed = parse_comment(t.first_comment_body) if trusted(t.first_comment_by_bot, t.first_comment_association) else None
        if parsed:
            found.append((t.path, parsed[1], t.resolved))
    return found

async def set_status(pr: PullRequestRef, sha: str, state: str, description: str, token: str, api_url: str,
                     target_url: Optional[str] = None) -> bool:
    """Set the merge check's status; whether that worked (it's said why, if not)"""
    try:
        await api.set_commit_status(pr.repo, sha, state, description, target_url=target_url, token=token, api_url=api_url)
        return True
    except GitHubError as e:
        print(f"codemop: couldn't set the merge check: {e}", file=sys.stderr)
        return False

async def repo_settings(pr: PullRequestRef, token: str, api_url: str) -> RepoConfig:
    """The repository's .codemop.yml from its default branch (the defaults if it's missing or broken)"""
    text = await api.fetch_repo_file(pr.repo, CONFIG_FILE, token=token, api_url=api_url)
    try:
        return parse_config(text, source=f"{pr.repo}/{CONFIG_FILE}") if text else RepoConfig()
    except ConfigError as e:
        print(f"codemop: using the default settings: {e}", file=sys.stderr)
        return RepoConfig()

NOT_REVIEWED = ("The latest commit hasn't been reviewed yet, so the merge check stays as it is. It's updated when "
                "the review of that commit finishes; comment `/codemop check` again after that if you need to.")

async def check_after_change(pr: PullRequestRef, sha: str, auth: dict) -> Optional[str]:
    """
    After a change that doesn't get a review (CodeMop's own commit, or a conversation resolved),
    set the merge check on `sha` from the summary and the conversations as they are now. Only
    on the commit the summary describes: anything else hasn't been reviewed, and setting the
    check there would let it pass unreviewed code. Returns why it wasn't set, if that matters.
    """
    config = await repo_settings(pr, **auth)
    if not config.merge_check:
        return None
    summary = find_summary(await api.list_issue_comments(pr, **auth))
    state = read_state(summary.body if summary else None)
    if not state.kept:
        return None  # not reviewed yet: the review will set it
    if state.commit != sha:
        return NOT_REVIEWED
    sync_threads(state, conversations(await api.list_review_threads(pr, **auth)))
    result, description = merge_status(state, config.merge_check_confidence)
    return None if await set_status(pr, sha, result, description, **auth) else "couldn't set the merge check"

async def record_commit(pr: PullRequestRef, parent: str, commit: str, auth: dict) -> None:
    """After CodeMop's own commit on `parent`: record it as reviewed if it can be, then set the merge check on it"""
    summary = find_summary(await api.list_issue_comments(pr, **auth))
    body = record_own_commit(summary.body, parent, commit) if summary else None
    if body:
        await api.post_issue_comment(pr, body, comment_id=summary.id, **auth)
    why = await check_after_change(pr, commit, auth)
    if why:
        print(f"Merge check not updated: {why}")
