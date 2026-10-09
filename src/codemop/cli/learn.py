"""codemop learn: act on a `/codemop learn <why>` reply to one of CodeMop's comments."""
import sys

from codemop.cli.common import WRITE_PERMISSIONS, github_token, record_commit
from codemop.github import api
from codemop.github.api import GitHubError, parse_pr_reference
from codemop.github.review import parse_comment
from codemop.github.summary import (
    trusted,
)
from codemop.review.learned import (
    LEARNED_FILE,
    Learned,
    add_learned,
    learned_yaml,
)

LEARN_COMMAND = "/codemop learn"

async def run_learn(args) -> int:
    """
    Act on a `/codemop learn <why>` reply to one of CodeMop's comments: add a note to the
    learned file on the PR's branch, resolve the conversation, and reply saying what happened
    """
    try:
        pr = parse_pr_reference(args.target)
    except ValueError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 2
    token = github_token()
    if not token:
        print("codemop: learn needs a GitHub token: set GITHUB_TOKEN (or `gh auth login`)", file=sys.stderr)
        return 2
    auth = dict(token=token, api_url=args.github_api_url)

    async def reply(text: str) -> None:
        await api.reply_to_review_comment(pr, args.comment, text, **auth)
        print(text)

    try:
        # The reply and what it replies to, read from GitHub (not trusted from the event)
        command = await api.fetch_review_comment(pr.repo, args.comment, **auth)
        parent = await api.fetch_review_comment(pr.repo, command.in_reply_to, **auth) if command and command.in_reply_to else None
        parsed = parse_comment(parent.body) if parent and trusted(parent.author_is_bot, parent.author_association) else None
        if not command or not command.body.strip().startswith(LEARN_COMMAND) or not parsed:
            print("Not a `/codemop learn` reply to one of CodeMop's comments; nothing to do")
            return 0
        reason = command.body.strip()[len(LEARN_COMMAND):].strip()
        if not reason:
            await reply(f"Say why it's fine, so the note makes sense to the next person: `{LEARN_COMMAND} <why it's fine>`.")
            return 0
        if await api.user_permission(pr.repo, command.author, **auth) not in WRITE_PERMISSIONS:
            await reply(f"Only people with write access to {pr.repo} can teach CodeMop. Resolving this conversation "
                        "dismisses it for this pull request.")
            return 0

        entry = Learned(parent.path, parsed[1], reason, f"#{pr.number}, @{command.author}")
        thread = next((t for t in await api.list_review_threads(pr, **auth) if t.first_comment_id == parent.id), None)
        pull = await api.fetch_pull_request(pr, **auth)
        if pull.head_repo != pr.repo:
            if thread:
                await api.resolve_thread(thread.id, **auth)
            await reply("I can't commit to a fork's branch, so I've only resolved this conversation (I won't raise it "
                        f"again on this PR). To teach the whole repository, add this to `{LEARNED_FILE}` on the "
                        f"default branch:\n\n```yaml\n{learned_yaml(entry).strip()}\n```")
            return 0

        for attempt in range(2):  # again if the branch moves on while this runs
            pull = await api.fetch_pull_request(pr, **auth)
            text = await api.fetch_repo_file(pull.head_repo, LEARNED_FILE, ref=pull.head_sha, **auth)
            message = f"Teach CodeMop: {entry.issue}\n\n{entry.reason}\n\nFrom @{command.author} on #{pr.number}."
            try:
                commit = await api.commit_files(pull.head_repo, pull.head_ref, pull.head_sha,
                                            {LEARNED_FILE: add_learned(text, entry)}, message, **auth)
                break
            except GitHubError as e:
                if e.status != 422 or attempt:
                    raise
        if thread:
            await api.resolve_thread(thread.id, **auth)
        await record_commit(pr, pull.head_sha, commit, auth)  # no review runs on CodeMop's own commit
        await reply(f"Learned: I've added this to `{LEARNED_FILE}` on this branch ({commit[:7]}) and resolved this "
                    "conversation. Once this PR is merged, I won't raise it again in this repository. If that's too "
                    "broad, edit or delete the note in that file.")
    except GitHubError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 1
    return 0
