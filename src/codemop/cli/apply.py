"""codemop apply: commit the fixes ticked in CodeMop's summary on a pull request."""
import sys

from codemop.cli.common import WRITE_PERMISSIONS, github_token, record_commit
from codemop.github import api
from codemop.github.api import GitHubError, PullRequest, parse_pr_reference
from codemop.github.summary import (
    find_summary,
    record_applied,
    stored_fixes,
    ticked,
)
from codemop.review.fixes import apply_fixes


async def run_apply(args) -> int:
    """Commit the fixes ticked in CodeMop's summary on a PR, as one commit, and mark them in the summary"""
    try:
        pr = parse_pr_reference(args.target)
    except ValueError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 2
    token = github_token()
    if not token:
        print("codemop: apply needs a GitHub token: set GITHUB_TOKEN (or `gh auth login`)", file=sys.stderr)
        return 2
    auth = dict(token=token, api_url=args.github_api_url)
    try:
        if args.by and await api.user_permission(pr.repo, args.by, **auth) not in WRITE_PERMISSIONS:
            print(f"Not applying fixes for {args.by}: only people with write access to {pr.repo} can")
            return 0
        summary = find_summary(await api.list_issue_comments(pr, **auth))
        fixes = stored_fixes(summary.body) if summary else {}
        wanted = [fixes[i] for i in sorted(ticked(summary.body)) if i in fixes] if summary else []
        if not wanted:
            print(f"No ticked fixes to apply on {pr}")
            return 0

        for attempt in range(2):  # again if the branch moves on while this runs
            pull = await api.fetch_pull_request(pr, **auth)
            if pull.head_repo != pr.repo:
                print(f"Can't commit to {pr}'s branch: it's in a fork ({pull.head_repo})")
                return 0
            files, applied, skipped = await _apply_to_files(pull, wanted, auth)
            commit = pull.head_sha
            if not files:
                break
            message = "Apply CodeMop's suggested fixes\n\n" + "\n".join(f"- {f.path}:{f.line}: {f.title}" for f in applied)
            if args.by:
                message += f"\n\nTicked by @{args.by} in CodeMop's summary on #{pr.number}."
            try:
                commit = await api.commit_files(pull.head_repo, pull.head_ref, pull.head_sha, files, message, **auth)
                break
            except GitHubError as e:
                if e.status != 422 or attempt:
                    raise

        # Mark the summary as it is now, not as it was read: more boxes may have been ticked meanwhile
        # (they stay ticked, for the next run), or a newer review may have updated it (findings keep
        # their ids, so the marks still go on the right ones)
        latest = find_summary(await api.list_issue_comments(pr, **auth)) or summary
        await api.post_issue_comment(pr, record_applied(latest.body, commit, applied, skipped), comment_id=latest.id, **auth)
        if applied:
            await record_commit(pr, pull.head_sha, commit, auth)  # no review runs on CodeMop's own commit
    except GitHubError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 1
    for fix in applied:
        print(f"Applied {fix.path}:{fix.line}: {fix.title}")
    for fix, reason in skipped:
        print(f"Not applied {fix.path}:{fix.line}: {reason}")
    if applied:
        print(f"Committed {commit[:7]} to {pull.head_ref}")
    return 0

async def _apply_to_files(pull: PullRequest, wanted, auth: dict):
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
