"""
The codemop command.

    codemop review owner/repo#123          review a pull request
    codemop review https://github.com/owner/repo/pull/123
    codemop review owner/repo#123 --post   ...and post the review on it
    git diff main | codemop review -       review a local diff

Exit status: 0 when every part of the diff was reviewed, 1 when some of it couldn't be
(see the report), 2 for usage errors.
"""
import argparse
import asyncio
import dataclasses
import json
import os
import shutil
import subprocess  # nosec B404
import sys
import textwrap
from enum import Enum
from pathlib import Path
from typing import List, Optional

from codemop import __version__
from codemop.config import (
    CONFIG_FILE, DEFAULT_MIN_CONFIDENCE, ConfigError, RepoConfig, load_config_file, parse_config,
)
from codemop.github.client import (
    DEFAULT_API_URL, GitHubError, PullRequestRef, fetch_pr_diff, fetch_pull_request, fetch_repo_file,
    fetch_review_bodies, parse_pr_reference, post_review,
)
from codemop.github.review import already_reviewed, review_payload
from codemop.providers import DEFAULT_MODELS, PROVIDERS, create_model
from codemop.providers.base import DEFAULT_CHUNK_TOKENS, Usage
from codemop.providers.pricing import PRICES_AS_OF
from codemop.review.chunks import DEFAULT_IGNORED_PATHS
from codemop.review.pipeline import ReviewReport, review_diff


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codemop", description="AI code review for pull requests.")
    parser.add_argument("--version", action="version", version=f"codemop {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    review = commands.add_parser(
        "review", help="review a pull request or a diff",
        description=(
            "Review a pull request (owner/repo#123 or a PR URL), or a diff on stdin (-). "
            f"How the repository is reviewed comes from its {CONFIG_FILE} (on the default branch; "
            "for stdin, the current directory), unless overridden here. Which model reviews it is "
            "up to you: --provider/--model, or CODEMOP_PROVIDER / CODEMOP_MODEL / CODEMOP_BASE_URL."
        ),
    )
    review.add_argument("target", help="owner/repo#123, a pull request URL, or - to read a diff from stdin")

    who = review.add_argument_group("model and cost (chosen by you, never by the repository)")
    who.add_argument("--provider", choices=PROVIDERS, default=os.environ.get("CODEMOP_PROVIDER", "anthropic"),
                     help="model provider (default: $CODEMOP_PROVIDER, or anthropic)")
    who.add_argument("--model", default=os.environ.get("CODEMOP_MODEL"),
                     help="model name (default: $CODEMOP_MODEL, or the provider's: "
                          + ", ".join(f"{p}: {m}" for p, m in DEFAULT_MODELS.items()) + ")")
    who.add_argument("--base-url", default=os.environ.get("CODEMOP_BASE_URL"),
                     help="API base URL, for openai-compatible or a self-hosted endpoint (default: $CODEMOP_BASE_URL)")
    who.add_argument("--api-key-env", help="environment variable holding the provider's API key")
    who.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                     default=os.environ.get("CODEMOP_EFFORT"),
                     help="how hard Claude thinks: lower is cheaper and faster (default: $CODEMOP_EFFORT, or high)")

    how = review.add_argument_group(f"review settings (override the repository's {CONFIG_FILE})")
    how.add_argument("--config", type=Path, metavar="PATH",
                     help=f"use this config file instead of the repository's {CONFIG_FILE}")
    how.add_argument("--min-confidence", type=float,
                     help=f"drop suggestions the model is less sure of (0-1, default: {DEFAULT_MIN_CONFIDENCE})")
    how.add_argument("--chunk-tokens", type=int,
                     help=f"largest piece of diff sent in one request (default: {DEFAULT_CHUNK_TOKENS:,}; 8,000 for ollama)")
    who.add_argument("--max-changed-lines", type=int, metavar="N",
                     help="don't review a diff with more added and removed lines than this (a cost limit)")
    how.add_argument("--max-comments", type=int, metavar="N",
                     help="with --post, the most inline comments (default: 10); the rest go in the summary")
    how.add_argument("--ignore", action="append", metavar="PATTERN",
                     help="another path pattern not to review (repeatable; added to the defaults: "
                          + " ".join(DEFAULT_IGNORED_PATHS) + ")")

    review.add_argument("--github-api-url", default=DEFAULT_API_URL, help="for GitHub Enterprise Server")
    review.add_argument("--json", action="store_true", help="print the report as JSON")
    review.add_argument("--post", action="store_true",
                        help="post the review on the pull request (needs a token with pull-requests: write); "
                             "a commit CodeMop has already reviewed isn't reviewed again")
    return parser


def _to_jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value):
        return {f.name: _to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    return value


def report_json(report: ReviewReport, target: str, config_source: str) -> str:
    return json.dumps(
        {"target": target, "config": config_source, "complete": report.complete, **_to_jsonable(report)},
        indent=2,
    )


def format_cost(cost: Optional[float], usage: Usage) -> str:
    if not usage.input_tokens and not usage.output_tokens:
        return "nothing spent"
    if cost is None:
        return "cost unknown for this model"
    if cost == 0:
        return "no cost (local model)"
    return f"about ${cost:.2f}" if cost >= 0.01 else "under $0.01"


def report_text(report: ReviewReport, target: str, config_source: str) -> str:
    settings = "" if config_source == "defaults" else f" (settings from {config_source})"
    lines: List[str] = [f"CodeMop review of {target} with {report.model}{settings}", ""]
    if report.too_large:
        lines.append(f"Not reviewed: {report.too_large}.")
    elif not report.suggestions:
        lines.append("No issues found." if report.complete else "No issues found in the parts that were reviewed.")
    for s in report.suggestions:
        location = f"{s.file_path}:{s.line}" + (f"-{s.end_line}" if s.end_line and s.end_line != s.line else "")
        lines.append(f"{location}  [{s.severity.value}, confidence {s.confidence:.2f}]  {s.title}")
        lines.extend(textwrap.wrap(s.explanation, width=88, initial_indent="    ", subsequent_indent="    "))
        if s.suggested_code:
            lines.append("    Suggested change:")
            lines.extend("      " + code_line for code_line in s.suggested_code.splitlines())
        lines.append("")

    notes: List[str] = []
    # The chunk that hit the fatal error, and those not started after it, share one note
    stopped = [f for f in report.failed if report.stopped and (f.kind == "not_reviewed" or f.reason == report.stopped)]
    if stopped:
        paths = ", ".join(path for failed in stopped for path in failed.paths)
        notes.append(f"Stopped early: {report.stopped} (not reviewed: {paths})")
    for failed in report.failed:
        if failed not in stopped:
            notes.append(f"Not reviewed ({', '.join(failed.paths)}): {failed.reason}")
    for skipped in report.skipped:
        notes.append(f"Skipped {skipped.path}: {skipped.reason}")
    if report.unplaced:
        notes.append(f"Set aside {len(report.unplaced)} suggestion(s) that pointed at lines outside the diff")
    if report.below_confidence:
        notes.append(f"Dropped {report.below_confidence} suggestion(s) below the confidence threshold")
    for dropped in report.dropped_fixes:
        notes.append(f"Left out the suggested fix for {dropped.file_path}:{dropped.line}: {dropped.reason}")
    if notes:
        lines += notes + [""]

    u = report.usage
    lines.append(f"{len(report.suggestions)} suggestion(s) · {report.chunks} chunk(s) · "
                 f"{u.input_tokens:,} input / {u.output_tokens:,} output tokens · "
                 f"{format_cost(report.cost, u)}" + ("" if not report.cost else f" (list prices as of {PRICES_AS_OF})"))
    return "\n".join(lines)


async def load_config(args, pr: Optional[PullRequestRef], token: Optional[str]) -> tuple[RepoConfig, str]:
    """The review settings and where they came from: --config, the repo's file, or the defaults"""
    if args.config:
        config = load_config_file(args.config)
        if config is None:
            raise ConfigError(f"{args.config} doesn't exist")
        return config, str(args.config)
    if pr is None:
        config = load_config_file(Path(CONFIG_FILE))
        return (config, CONFIG_FILE) if config else (RepoConfig(), "defaults")
    text = await fetch_repo_file(pr.repo, CONFIG_FILE, token=token, api_url=args.github_api_url)
    if text is None:
        return RepoConfig(), "defaults"
    return parse_config(text, source=f"{pr.repo}/{CONFIG_FILE}"), f"{pr.repo}/{CONFIG_FILE}"


async def run_review(args) -> int:
    pr = None
    token = None
    if args.target != "-":
        try:
            pr = parse_pr_reference(args.target)
        except ValueError as e:
            print(f"codemop: {e}", file=sys.stderr)
            return 2
        token = github_token()
    if args.post and (pr is None or not token):
        problem = "a pull request to post on, not a diff" if pr is None else "a GitHub token: set GITHUB_TOKEN (or `gh auth login`)"
        print(f"codemop: --post needs {problem}", file=sys.stderr)
        return 2

    try:
        config, config_source = await load_config(args, pr, token)
    except (ConfigError, GitHubError) as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 2 if isinstance(e, ConfigError) else 1

    head_sha = None
    if pr is None:
        diff, target = sys.stdin.read(), "stdin"
    else:
        target = str(pr)
        try:
            if args.post:
                # The commit the review's line numbers will refer to, read before the diff
                head_sha = (await fetch_pull_request(pr, token=token, api_url=args.github_api_url)).head_sha
                reviews = await fetch_review_bodies(pr, token=token, api_url=args.github_api_url)
                if already_reviewed(reviews, head_sha):
                    print(f"CodeMop has already reviewed {target} at {head_sha[:7]}; nothing to do")
                    return 0
            diff = await fetch_pr_diff(pr, token=token, api_url=args.github_api_url)
        except GitHubError as e:
            print(f"codemop: {e}", file=sys.stderr)
            return 1

    try:
        model = create_model(
            args.provider, args.model, base_url=args.base_url, api_key_env=args.api_key_env, effort=args.effort
        )
    except ValueError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 2

    report = await review_diff(
        diff, model,
        chunk_tokens=args.chunk_tokens or config.chunk_tokens,
        min_confidence=args.min_confidence if args.min_confidence is not None else config.min_confidence,
        ignored_paths=[*DEFAULT_IGNORED_PATHS, *config.ignore, *(args.ignore or [])],
        max_changed_lines=args.max_changed_lines,
    )
    print(report_json(report, target, config_source) if args.json else report_text(report, target, config_source))
    if args.post:
        if report.stopped:
            print(f"codemop: not posting a review: {report.stopped}", file=sys.stderr)
            return 1
        try:
            url = await post(pr, report, head_sha, token, args.max_comments or config.max_comments, args.github_api_url)
        except GitHubError as e:
            print(f"codemop: {e}", file=sys.stderr)
            return 1
        print(f"Posted the review: {url}", file=sys.stderr if args.json else sys.stdout)
    # Too large to review is a deliberate limit, not a failure
    return 0 if report.complete or report.too_large else 1


async def post(pr: PullRequestRef, report: ReviewReport, head_sha: str, token: str, max_comments: int,
               api_url: str) -> str:
    """Post the review; if GitHub won't take the inline comments, the summary alone (it lists them all)"""
    payload = review_payload(report, head_sha, format_cost(report.cost, report.usage), max_comments)
    try:
        return await post_review(pr, payload, token=token, api_url=api_url)
    except GitHubError as e:
        if e.status != 422 or not payload["comments"]:
            raise
    payload["body"] += ("\n\n⚠️ GitHub didn't accept the inline comments (has the PR changed since it was "
                        "reviewed?), so they're only listed above.")
    payload["comments"] = []
    return await post_review(pr, payload, token=token, api_url=api_url)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "review":
        return asyncio.run(run_review(args))
    return 2


if __name__ == "__main__":
    sys.exit(main())
