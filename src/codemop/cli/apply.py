"""codemop apply: commit the fixes ticked in CodeMop's summary on a pull request."""
from typing import List, Tuple

from codemop.cli.common import can_write, commit_to_branch, record_commit, start, update_summary
from codemop.github import api
from codemop.github.api import PullRequest
from codemop.github.checklist import commit_requested, record_applied, stored_fixes, ticked, untick_commit
from codemop.github.summary import find_summary
from codemop.review.fixes import Fix, apply_fixes


async def run_apply(args) -> int:
    """Commit the fixes ticked in CodeMop's summary on a PR, as one commit, and mark them in the summary"""
    pr, auth = start(args, "apply")
    summary = find_summary(await api.list_issue_comments(pr, **auth))
    if not summary or not commit_requested(summary.body):
        # Ticking a fix only selects it; nothing happens until "Commit the ticked fixes" is ticked
        print(f"\"Commit the ticked fixes\" isn't ticked on {pr}; nothing to do")
        return 0
    if args.by and not await can_write(pr, args.by, auth):
        print(f"Not applying fixes for {args.by}: only people with write access to {pr.repo} can")
        return 0
    fixes = stored_fixes(summary.body)
    wanted = [fixes[i] for i in sorted(ticked(summary.body)) if i in fixes]
    if not wanted:
        print(f"No ticked fixes to apply on {pr}")
        await update_summary(pr, auth, untick_commit)
        return 0

    applied: List[Fix] = []
    skipped: List[Tuple[Fix, str]] = []

    async def build(pull: PullRequest):
        nonlocal applied, skipped
        files, applied, skipped = await _apply_to_files(pull, wanted, auth)
        message = "Apply CodeMop's suggested fixes\n\n" + "\n".join(f"- {f.path}:{f.line}: {f.title}" for f in applied)
        if args.by:
            message += f"\n\nTicked by @{args.by} in CodeMop's summary on #{pr.number}."
        return files, message

    pull, commit = await commit_to_branch(pr, auth, build)
    if pull.head_repo != pr.repo:
        print(f"Can't commit to {pr}'s branch: it's in a fork ({pull.head_repo})")
        return 0
    # Marked on the summary as it is now, not as it was read: more boxes may have been ticked
    # meanwhile (they stay ticked, for the next run), or a newer review may have updated it
    # (findings keep their ids, so the marks still go on the right ones)
    def mark(body: str) -> str:
        return record_applied(body, commit or pull.head_sha, applied, skipped)

    if commit:
        await record_commit(pr, auth, pull.head_sha, commit, mark)  # no review runs on CodeMop's own commit
    else:
        await update_summary(pr, auth, mark)
    for fix in applied:
        print(f"Applied {fix.path}:{fix.line}: {fix.title}")
    for fix, reason in skipped:
        print(f"Not applied {fix.path}:{fix.line}: {reason}")
    if commit:
        print(f"Committed {commit[:7]} to {pull.head_ref}")
    return 0


async def _apply_to_files(pull: PullRequest, wanted: List[Fix], auth: dict):
    """The new text of each file the fixes change, and which fixes were applied and skipped"""
    files, applied, skipped = {}, [], []
    for path in dict.fromkeys(f.path for f in wanted):
        for_path = [f for f in wanted if f.path == path]
        text = await api.fetch_repo_file(pull.head_repo, path, ref=pull.head_sha, **auth)
        if text is None:
            skipped += [(f, "the file no longer exists") for f in for_path]
            continue
        result = apply_fixes(text, for_path)
        applied += result.applied
        skipped += result.skipped
        if result.applied:
            files[path] = result.text
    return files, applied, skipped
