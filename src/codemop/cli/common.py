"""What the commands share: getting started, the repository's settings, updating the summary,
committing to the PR's branch, and the merge check."""
import os
import shutil
import subprocess  # nosec B404
import sys
from typing import Awaitable, Callable, List, Optional, Sequence, Tuple

from codemop.config import CONFIG_FILE, ConfigError, RepoConfig, parse_config
from codemop.github import api
from codemop.github.api import GitHubError, PullRequest, PullRequestRef, ReviewThread
from codemop.github.check import merge_status
from codemop.github.checklist import record_own_commit
from codemop.github.review import CodemopComment, codemop_comment
from codemop.github.summary import find_summary, read_state, sync_threads

WRITE_PERMISSIONS = {"admin", "maintain", "write"}
NOT_REVIEWED = ("The latest commit hasn't been reviewed yet, so the merge check stays as it is. It's updated when "
                "the review of that commit finishes; comment `/codemop check` again after that if you need to.")


class CommandError(Exception):
    """
    A command can't run: the message says why, and `code` is the exit status (2 for usage
    errors). (A GitHubError a command doesn't handle is reported the same way, with status 1.)
    """

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


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


def pr_reference(target: str) -> PullRequestRef:
    try:
        return api.parse_pr_reference(target)
    except ValueError as e:
        raise CommandError(str(e))


def start(args, command: str) -> Tuple[PullRequestRef, dict]:
    """For a command on a pull request: the PR, and the token and API to use (`auth`)"""
    pr = pr_reference(args.target)
    token = github_token()
    if not token:
        raise CommandError(f"{command} needs a GitHub token: set GITHUB_TOKEN (or `gh auth login`)")
    return pr, dict(token=token, api_url=args.github_api_url)


async def repo_config(pr: PullRequestRef, auth: dict, lenient: bool = False) -> Tuple[RepoConfig, str]:
    """
    The repository's .codemop.yml from its default branch, and where it came from ("defaults"
    if there isn't one). A broken file is a ConfigError, or with `lenient` the defaults.
    """
    text = await api.fetch_repo_file(pr.repo, CONFIG_FILE, **auth)
    if text is None:
        return RepoConfig(), "defaults"
    source = f"{pr.repo}/{CONFIG_FILE}"
    try:
        return parse_config(text, source=source), source
    except ConfigError as e:
        if not lenient:
            raise
        print(f"codemop: using the default settings: {e}", file=sys.stderr)
        return RepoConfig(), "defaults"


async def can_write(pr: PullRequestRef, user: str, auth: dict) -> bool:
    return await api.user_permission(pr.repo, user, **auth) in WRITE_PERMISSIONS


def conversations(threads: Sequence[ReviewThread]) -> List[Tuple[CodemopComment, ReviewThread]]:
    """The threads CodeMop started, with what each is about"""
    found = []
    for thread in threads:
        comment = codemop_comment(thread.first_comment_body, thread.first_comment_by_bot,
                                  thread.first_comment_association)
        if comment:
            found.append((comment, thread))
    return found


def thread_states(threads: Sequence[ReviewThread]) -> List[Tuple[Optional[int], str, str, bool]]:
    """(finding id, path, title, resolved) for CodeMop's threads, for summary.sync_threads"""
    return [(c.finding_id, t.path, c.title, t.resolved) for c, t in conversations(threads)]


async def update_summary(pr: PullRequestRef, auth: dict, edit: Callable[[str], Optional[str]]) -> Optional[str]:
    """
    Read the summary as it is now, edit it (`edit` returns the new text, or None to leave it),
    and write it back if it changed; returns its text after. Reading it fresh means changes made
    meanwhile (boxes ticked, a newer review) are kept, whatever the edit.
    """
    summary = find_summary(await api.list_issue_comments(pr, **auth))
    if summary is None:
        return None
    body = edit(summary.body)
    if body is None or body == summary.body:
        return summary.body
    await api.post_issue_comment(pr, body, comment_id=summary.id, **auth)
    return body


async def commit_to_branch(
    pr: PullRequestRef, auth: dict, build: Callable[[PullRequest], Awaitable[Tuple[dict, str]]],
) -> Tuple[PullRequest, Optional[str]]:
    """
    Commit to the PR's branch, through the API (nothing is checked out). `build(pull)` gives
    the files (path: text) and the commit message, from the PR as it is now. Returns the PR as
    it was committed on, and the new commit (None for a fork's branch, which can't be committed
    to, or when there's nothing to commit). Tries again if the branch moves on meanwhile.
    """
    for attempt in range(2):
        pull = await api.fetch_pull_request(pr, **auth)
        if pull.head_repo != pr.repo:
            return pull, None
        files, message = await build(pull)
        if not files:
            return pull, None
        try:
            return pull, await api.commit_files(pull.head_repo, pull.head_ref, pull.head_sha, files, message, **auth)
        except GitHubError as e:
            if e.status != 422 or attempt:
                raise
    raise AssertionError("unreachable")


async def set_status(pr: PullRequestRef, sha: str, state: str, description: str, auth: dict,
                     target_url: Optional[str] = None) -> bool:
    """Set the merge check's status; whether that worked (it's said why, if not)"""
    try:
        await api.set_commit_status(pr.repo, sha, state, description, target_url=target_url, **auth)
        return True
    except GitHubError as e:
        print(f"codemop: couldn't set the merge check: {e}", file=sys.stderr)
        return False


async def check_after_change(pr: PullRequestRef, sha: str, auth: dict, body: Optional[str] = None) -> Optional[str]:
    """
    After a change that doesn't get a review (CodeMop's own commit, or a conversation resolved),
    set the merge check on `sha` from the summary (`body`, if the caller has just written it)
    and the conversations as they are now. Only on the commit the summary describes: anything
    else hasn't been reviewed, and setting the check there would let it pass unreviewed code.
    Returns why it wasn't set, if that matters.
    """
    config, _ = await repo_config(pr, auth, lenient=True)
    if not config.merge_check:
        return None
    if body is None:
        summary = find_summary(await api.list_issue_comments(pr, **auth))
        body = summary.body if summary else None
    state = read_state(body)
    if state.commit is None:
        return None  # not reviewed yet: the review will set it
    if state.commit != sha:
        return NOT_REVIEWED
    sync_threads(state, thread_states(await api.list_review_threads(pr, **auth)))
    result, description = merge_status(state, config.merge_check_confidence)
    return None if await set_status(pr, sha, result, description, auth) else "couldn't set the merge check"


async def record_commit(pr: PullRequestRef, auth: dict, parent: str, commit: str,
                        edit: Callable[[str], str] = lambda body: body) -> None:
    """
    After CodeMop's own commit on `parent`: edit the summary (marking what the commit did) and
    record the commit as reviewed if it can be, in one write; then set the merge check on it
    """
    def edit_and_record(current: str) -> str:
        edited = edit(current)
        return record_own_commit(edited, parent, commit) or edited

    body = await update_summary(pr, auth, edit_and_record)
    why = await check_after_change(pr, commit, auth, body)
    if why:
        print(f"Merge check not updated: {why}")
