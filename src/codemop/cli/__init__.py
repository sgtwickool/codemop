"""
The codemop command.

    codemop review owner/repo#123          review a pull request
    codemop review https://github.com/owner/repo/pull/123
    codemop review owner/repo#123 --post   ...and post the review on it
    git diff main | codemop review -       review a local diff
    codemop apply owner/repo#123           commit the fixes ticked in CodeMop's summary on it
    codemop learn owner/repo#123 --comment ID   act on a `/codemop learn <why>` reply on it
    codemop check owner/repo#123           update its merge check (after a conversation is resolved, say)

Exit status: 0 when every part of the diff was reviewed, 1 when some of it couldn't be
(see the report), 2 for usage errors.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional

from codemop import __version__
from codemop.cli.apply import run_apply
from codemop.cli.check import run_check
from codemop.cli.common import CommandError
from codemop.cli.learn import run_learn
from codemop.cli.review import run_review
from codemop.config import CONFIG_FILE, DEFAULT_MIN_CONFIDENCE
from codemop.github.api import DEFAULT_API_URL, GitHubError
from codemop.providers import DEFAULT_MODELS, PROVIDERS
from codemop.providers.base import DEFAULT_CHUNK_TOKENS
from codemop.review.chunks import DEFAULT_IGNORED_PATHS
from codemop.review.learned import LEARNED_FILE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codemop", description="AI code review for pull requests.")
    parser.add_argument("--version", action="version", version=f"codemop {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    github = argparse.ArgumentParser(add_help=False)
    github.add_argument("--github-api-url", default=DEFAULT_API_URL, help="for GitHub Enterprise Server")

    review = commands.add_parser(
        "review", parents=[github], help="review a pull request or a diff",
        description=(
            "Review a pull request (owner/repo#123 or a PR URL), or a diff on stdin (-). "
            f"How the repository is reviewed comes from its {CONFIG_FILE} (on the default branch; "
            "for stdin, the current directory), unless overridden here. Which model reviews it is "
            "up to you: --provider/--model, or CODEMOP_PROVIDER / CODEMOP_MODEL / CODEMOP_BASE_URL."
        ),
    )
    review.add_argument("target", help="owner/repo#123, a pull request URL, or - to read a diff from stdin")
    review.set_defaults(run=run_review)

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
    how.add_argument("--context", action=argparse.BooleanOptionalAction, default=True,
                     help="send the code around each change too: whole functions, where the changed code is used "
                          "in other files, and definitions it uses (on by default; about 13%% more per review)")
    how.add_argument("--max-comments", type=int, metavar="N",
                     help="with --post, the most inline comments (default: 10); the rest go in the summary")
    how.add_argument("--ignore", action="append", metavar="PATTERN",
                     help="another path pattern not to review (repeatable; added to the defaults: "
                          + " ".join(DEFAULT_IGNORED_PATHS) + ")")

    review.add_argument("--json", action="store_true", help="print the report as JSON")
    review.add_argument("--post", action="store_true",
                        help="post the review on the pull request (needs a token with pull-requests: write); "
                             "a commit CodeMop has already reviewed isn't reviewed again")
    review.add_argument("--checklist", action="store_true",
                        help="with --post, a checkbox in the summary for each issue with a fix: ticking some and "
                             "running `codemop apply` commits them (the GitHub Action does that for you)")

    apply = commands.add_parser(
        "apply", parents=[github], help="commit the fixes ticked in CodeMop's summary on a pull request",
        description="Commit the fixes ticked in CodeMop's summary comment on a pull request to its branch, as one "
                    "commit. Needs a token with contents: write and pull-requests: write.",
    )
    apply.add_argument("target", help="owner/repo#123 or a pull request URL")
    apply.set_defaults(run=run_apply)
    apply.add_argument("--by", metavar="USER",
                       help="who ticked them: nothing is applied unless they have write access to the repository")

    learn = commands.add_parser(
        "learn", parents=[github], help="act on a `/codemop learn <why>` reply to one of CodeMop's comments",
        description=f"Act on a `/codemop learn <why>` reply to one of CodeMop's comments on a pull request: add a "
                    f"note to {LEARNED_FILE} on the PR's branch, resolve the conversation, and reply to confirm. "
                    "Needs a token with contents: write and pull-requests: write.",
    )
    learn.add_argument("target", help="owner/repo#123 or a pull request URL")
    learn.set_defaults(run=run_learn)
    learn.add_argument("--comment", type=int, required=True, metavar="ID", help="the reply's id")

    check = commands.add_parser(
        "check", parents=[github], help="update CodeMop's merge check on a pull request",
        description="Set CodeMop's merge check (a commit status, for repositories with `merge_check: true` in "
                    f"{CONFIG_FILE}) on a pull request's latest commit, from its summary and which of CodeMop's "
                    "conversations are resolved. Needs a token with statuses: write.",
    )
    check.add_argument("target", help="owner/repo#123 or a pull request URL")
    check.set_defaults(run=run_check)
    check.add_argument("--comment", type=int, metavar="ID",
                       help="the `/codemop check` comment that asked for it, to react to so its author knows it ran")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(args.run(args))
    except CommandError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return e.code
    except GitHubError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 1
