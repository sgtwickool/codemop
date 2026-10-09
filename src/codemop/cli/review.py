"""codemop review: review a pull request or a diff and print the report (with --post, see post.py)."""
import sys
from pathlib import Path
from typing import Optional, Tuple

from codemop import providers
from codemop.cli.common import CommandError, github_token, pr_reference, repo_config
from codemop.cli.report import report_json, report_text
from codemop.config import CONFIG_FILE, ConfigError, RepoConfig, load_config_file
from codemop.github import api
from codemop.github.api import GitHubError, PullRequestRef
from codemop.github.files import GitHubFiles
from codemop.providers.base import ReviewModel
from codemop.review.chunks import DEFAULT_IGNORED_PATHS
from codemop.review.context import FileSource, LocalFiles
from codemop.review.learned import LEARNED_FILE, Settled, parse_learned
from codemop.review.pipeline import ReviewReport, review_diff


async def run_review(args) -> int:
    pr = None if args.target == "-" else pr_reference(args.target)
    token = github_token() if pr else None
    if args.post and (pr is None or not token):
        problem = "a pull request to post on, not a diff" if pr is None else "a GitHub token: set GITHUB_TOKEN (or `gh auth login`)"
        raise CommandError(f"--post needs {problem}")
    auth = dict(token=token, api_url=args.github_api_url)
    try:  # before anything is fetched, so a mistyped provider or model fails at once
        model = providers.create_model(
            args.provider, args.model, base_url=args.base_url, api_key_env=args.api_key_env, effort=args.effort
        )
    except ValueError as e:
        raise CommandError(str(e))
    try:
        config, config_source = await load_config(args, pr, auth)
    except ConfigError as e:
        raise CommandError(str(e))

    if pr is None:
        context = LocalFiles(Path.cwd()) if args.context else None
        learned = Path(LEARNED_FILE)
        settled = Settled(learned=parse_learned(learned.read_text() if learned.is_file() else None))
        report = await review(args, config, model, sys.stdin.read(), settled, context)
        return print_report(args, report, "stdin", config_source)
    if args.post:
        from codemop.cli.post import review_and_post
        return await review_and_post(args, pr, auth, model, config, config_source)
    pull = await api.fetch_pull_request(pr, **auth) if args.context else None
    diff, learned = await fetch_diff_and_learned(pr, auth)
    context = GitHubFiles(pull.head_repo or pr.repo, pull.head_sha, **auth) if pull else None
    report = await review(args, config, model, diff, Settled(learned=learned), context)
    return print_report(args, report, str(pr), config_source)


async def load_config(args, pr: Optional[PullRequestRef], auth: dict) -> Tuple[RepoConfig, str]:
    """The review settings and where they came from: --config, the repo's file, or the defaults"""
    if args.config:
        config = load_config_file(args.config)
        if config is None:
            raise ConfigError(f"{args.config} doesn't exist")
        return config, str(args.config)
    if pr is None:
        config = load_config_file(Path(CONFIG_FILE))
        return (config, CONFIG_FILE) if config else (RepoConfig(), "defaults")
    return await repo_config(pr, auth)


async def fetch_diff_and_learned(pr: PullRequestRef, auth: dict):
    """The PR's diff, and the repository's learned notes (from its default branch)"""
    diff = await api.fetch_pr_diff(pr, **auth)
    try:
        learned = parse_learned(await api.fetch_repo_file(pr.repo, LEARNED_FILE, **auth))
    except GitHubError as e:  # not worth failing the review over: it may just raise something again
        print(f"codemop: couldn't read {LEARNED_FILE} ({e}); reviewing without it", file=sys.stderr)
        learned = []
    return diff, learned


async def review(args, config: RepoConfig, model: ReviewModel, diff: str, settled: Settled,
                 context: Optional[FileSource]) -> ReviewReport:
    """review_diff with the settings from the command line and the repository's config"""
    return await review_diff(
        diff, model,
        chunk_tokens=args.chunk_tokens or config.chunk_tokens,
        min_confidence=args.min_confidence if args.min_confidence is not None else config.min_confidence,
        ignored_paths=[*DEFAULT_IGNORED_PATHS, *config.ignore, *(args.ignore or [])],
        max_changed_lines=args.max_changed_lines,
        settled=settled,
        context=context,
    )


def print_report(args, report: ReviewReport, target: str, config_source: str) -> int:
    print(report_json(report, target, config_source) if args.json else report_text(report, target, config_source))
    # Too large to review is a deliberate limit, not a failure
    return 0 if report.complete or report.too_large else 1
