"""codemop check: update the merge check on a pull request."""
from codemop.cli.common import NOT_REVIEWED, check_after_change, start
from codemop.github import api


async def run_check(args) -> int:
    """Update the merge check on a PR's latest commit, from its summary and conversations"""
    pr, auth = start(args, "check")
    pull = await api.fetch_pull_request(pr, **auth)
    why = await check_after_change(pr, pull.head_sha, auth)
    if why == NOT_REVIEWED and args.comment:
        await api.post_issue_comment(pr, why, **auth)  # say why nothing changed, rather than leave them guessing
    elif args.comment and not why:
        await api.react_to_issue_comment(pr.repo, args.comment, "+1", **auth)
    print(why or "Merge check updated")
    return 1 if why and why != NOT_REVIEWED else 0
