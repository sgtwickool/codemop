"""
The codemop command.

    codemop review owner/repo#123          review a pull request
    codemop review https://github.com/owner/repo/pull/123
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
from typing import List, Optional

from codemop import __version__
from codemop.github.client import DEFAULT_API_URL, GitHubError, fetch_pr_diff, parse_pr_reference
from codemop.providers import DEFAULT_MODELS, PROVIDERS, create_model
from codemop.review.chunks import DEFAULT_IGNORED_PATHS
from codemop.providers.base import DEFAULT_CHUNK_TOKENS
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
        description="Review a pull request (owner/repo#123 or a PR URL), or a diff on stdin (-).",
    )
    review.add_argument("target", help="owner/repo#123, a pull request URL, or - to read a diff from stdin")
    review.add_argument("--provider", choices=PROVIDERS, default="anthropic",
                        help="model provider (default: anthropic)")
    review.add_argument("--model", help="model name (defaults: " + ", ".join(f"{p}: {m}" for p, m in DEFAULT_MODELS.items()) + ")")
    review.add_argument("--base-url", help="API base URL, for openai-compatible or a self-hosted endpoint")
    review.add_argument("--api-key-env", help="environment variable holding the provider's API key")
    review.add_argument("--min-confidence", type=float, default=0.5,
                        help="drop suggestions the model is less sure of (0-1, default: 0.5)")
    review.add_argument("--chunk-tokens", type=int,
                        help=f"largest piece of diff sent in one request (default: {DEFAULT_CHUNK_TOKENS:,}; 8,000 for ollama)")
    review.add_argument("--ignore", action="append", metavar="PATTERN",
                        help="path pattern to skip (repeatable; replaces the defaults: "
                             + " ".join(DEFAULT_IGNORED_PATHS) + ")")
    review.add_argument("--github-api-url", default=DEFAULT_API_URL, help="for GitHub Enterprise Server")
    review.add_argument("--json", action="store_true", help="print the report as JSON")
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


def report_json(report: ReviewReport, target: str) -> str:
    return json.dumps({"target": target, "complete": report.complete, **_to_jsonable(report)}, indent=2)


def report_text(report: ReviewReport, target: str) -> str:
    lines: List[str] = [f"CodeMop review of {target} with {report.model}", ""]
    if not report.suggestions:
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
    if report.stopped:
        # The chunk that hit the fatal error, and those not started after it, share one note
        stopped_paths = [
            path for failed in report.failed
            if failed.reason in (report.stopped, f"not reviewed: {report.stopped}")
            for path in failed.paths
        ]
        notes.append(f"Stopped early: {report.stopped} (not reviewed: {', '.join(stopped_paths)})")
    for failed in report.failed:
        if report.stopped and failed.reason in (report.stopped, f"not reviewed: {report.stopped}"):
            continue
        notes.append(f"Not reviewed ({', '.join(failed.paths)}): {failed.reason}")
    for skipped in report.skipped:
        notes.append(f"Skipped {skipped.path}: {skipped.reason}")
    if report.unplaced:
        notes.append(f"Set aside {len(report.unplaced)} suggestion(s) that pointed at lines outside the diff")
    if report.below_confidence:
        notes.append(f"Dropped {report.below_confidence} suggestion(s) below the confidence threshold")
    if notes:
        lines += notes + [""]

    u = report.usage
    lines.append(f"{len(report.suggestions)} suggestion(s) · {report.chunks} chunk(s) · "
                 f"{u.input_tokens:,} input / {u.output_tokens:,} output tokens")
    return "\n".join(lines)


async def run_review(args) -> int:
    if args.target == "-":
        diff, target = sys.stdin.read(), "stdin"
    else:
        try:
            pr = parse_pr_reference(args.target)
        except ValueError as e:
            print(f"codemop: {e}", file=sys.stderr)
            return 2
        target = str(pr)
        try:
            diff = await fetch_pr_diff(pr, token=github_token(), api_url=args.github_api_url)
        except GitHubError as e:
            print(f"codemop: {e}", file=sys.stderr)
            return 1

    try:
        model = create_model(args.provider, args.model, base_url=args.base_url, api_key_env=args.api_key_env)
    except ValueError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 2

    report = await review_diff(
        diff, model,
        chunk_tokens=args.chunk_tokens,
        min_confidence=args.min_confidence,
        ignored_paths=args.ignore if args.ignore else DEFAULT_IGNORED_PATHS,
    )
    print(report_json(report, target) if args.json else report_text(report, target))
    return 0 if report.complete else 1


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "review":
        return asyncio.run(run_review(args))
    return 2


if __name__ == "__main__":
    sys.exit(main())
