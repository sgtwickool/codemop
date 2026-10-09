"""codemop learn: act on a `/codemop learn <why>` reply to one of CodeMop's comments."""
from codemop.cli.common import can_write, commit_to_branch, record_commit, start
from codemop.github import api
from codemop.github.api import PullRequest
from codemop.github.review import codemop_comment
from codemop.review.learned import LEARNED_FILE, Learned, add_learned, learned_yaml

LEARN_COMMAND = "/codemop learn"


async def run_learn(args) -> int:
    """
    Act on a `/codemop learn <why>` reply to one of CodeMop's comments: add a note to the
    learned file on the PR's branch, resolve the conversation, and reply saying what happened
    """
    pr, auth = start(args, "learn")

    async def reply(text: str) -> None:
        await api.reply_to_review_comment(pr, args.comment, text, **auth)
        print(text)

    # The reply and what it replies to, read from GitHub (not trusted from the event)
    command = await api.fetch_review_comment(pr.repo, args.comment, **auth)
    parent = await api.fetch_review_comment(pr.repo, command.in_reply_to, **auth) if command and command.in_reply_to else None
    about = codemop_comment(parent.body, parent.author_is_bot, parent.author_association) if parent else None
    if not command or not command.body.strip().startswith(LEARN_COMMAND) or not about:
        print("Not a `/codemop learn` reply to one of CodeMop's comments; nothing to do")
        return 0
    reason = command.body.strip()[len(LEARN_COMMAND):].strip()
    if not reason:
        await reply(f"Say why it's fine, so the note makes sense to the next person: `{LEARN_COMMAND} <why it's fine>`.")
        return 0
    if not await can_write(pr, command.author, auth):
        await reply(f"Only people with write access to {pr.repo} can teach CodeMop. Resolving this conversation "
                    "dismisses it for this pull request.")
        return 0

    entry = Learned(parent.path, about.title, reason, f"#{pr.number}, @{command.author}")

    async def build(pull: PullRequest):
        text = await api.fetch_repo_file(pull.head_repo, LEARNED_FILE, ref=pull.head_sha, **auth)
        message = f"Teach CodeMop: {entry.issue}\n\n{entry.reason}\n\nFrom @{command.author} on #{pr.number}."
        return {LEARNED_FILE: add_learned(text, entry)}, message

    pull, commit = await commit_to_branch(pr, auth, build)
    thread = next((t for t in await api.list_review_threads(pr, **auth) if t.first_comment_id == parent.id), None)
    if thread and not thread.resolved:
        await api.resolve_thread(thread.id, **auth)
    if commit is None:  # a fork's branch
        await reply("I can't commit to a fork's branch, so I've only resolved this conversation (I won't raise it "
                    f"again on this PR). To teach the whole repository, add this to `{LEARNED_FILE}` on the "
                    f"default branch:\n\n```yaml\n{learned_yaml(entry).strip()}\n```")
        return 0
    await record_commit(pr, auth, pull.head_sha, commit)  # no review runs on CodeMop's own commit
    await reply(f"Learned: I've added this to `{LEARNED_FILE}` on this branch ({commit[:7]}) and resolved this "
                "conversation. Once this PR is merged, I won't raise it again in this repository. If that's too "
                "broad, edit or delete the note in that file.")
    return 0
