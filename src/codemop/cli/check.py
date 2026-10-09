"""codemop check: update the merge check on a pull request."""
import sys

from codemop.cli.common import NOT_REVIEWED, check_after_change, github_token
from codemop.github import api
from codemop.github.api import GitHubError, parse_pr_reference


async def run_check(args) -> int:
    """Update the merge check on a PR's latest commit, from its summary and conversations"""
    try:
        pr = parse_pr_reference(args.target)
    except ValueError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 2
    token = github_token()
    if not token:
        print("codemop: check needs a GitHub token: set GITHUB_TOKEN (or `gh auth login`)", file=sys.stderr)
        return 2
    auth = dict(token=token, api_url=args.github_api_url)
    try:
        pull = await api.fetch_pull_request(pr, **auth)
        why = await check_after_change(pr, pull.head_sha, auth)
        if why == NOT_REVIEWED and args.comment:
            await api.post_issue_comment(pr, why, **auth)  # say why nothing changed, rather than leave them guessing
        elif args.comment and not why:
            await api.react_to_issue_comment(pr.repo, args.comment, "+1", **auth)
        print(why or "Merge check updated")
        return 1 if why and why != NOT_REVIEWED else 0
    except GitHubError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 1
