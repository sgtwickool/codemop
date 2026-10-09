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
import dataclasses
import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import textwrap
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from codemop import __version__
from codemop.config import (
    CONFIG_FILE, DEFAULT_MIN_CONFIDENCE, ConfigError, RepoConfig, load_config_file, parse_config,
)
from codemop.github.client import (
    DEFAULT_API_URL, GitHubError, PullRequest, PullRequestRef, ReviewThread, commit_files, compare_commits,
    fetch_pr_diff, fetch_pull_request, fetch_repo_file, fetch_review_comment, list_issue_comments,
    list_review_threads, parse_pr_reference, post_issue_comment, post_review, reply_to_review_comment,
    react_to_issue_comment, resolve_thread, set_commit_status, user_permission,
)
from codemop.github.check import merge_status
from codemop.github.review import parse_comment, ranked, review_payload
from codemop.github.summary import (
    OPEN, SummaryState, find_summary, read_state, record_applied, record_own_commit, stored_fixes, summary_body,
    sync_threads, ticked, trusted, update_earlier,
)
from codemop.review.placement import place_suggestions
from codemop.review.schema import Severity
from codemop.review.learned import (
    LEARNED_FILE, Dismissed, Learned, Settled, add_learned, learned_yaml, parse_learned,
)
from codemop.review.diff import parse_diff
from codemop.review.fixes import apply_fixes, file_lines
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
    review.add_argument("--checklist", action="store_true",
                        help="with --post, a checkbox in the summary for each issue with a fix: ticking some and "
                             "running `codemop apply` commits them (the GitHub Action does that for you)")

    apply = commands.add_parser(
        "apply", help="commit the fixes ticked in CodeMop's summary on a pull request",
        description="Commit the fixes ticked in CodeMop's summary comment on a pull request to its branch, as one "
                    "commit. Needs a token with contents: write and pull-requests: write.",
    )
    apply.add_argument("target", help="owner/repo#123 or a pull request URL")
    apply.add_argument("--by", metavar="USER",
                       help="who ticked them: nothing is applied unless they have write access to the repository")
    apply.add_argument("--github-api-url", default=DEFAULT_API_URL, help="for GitHub Enterprise Server")

    learn = commands.add_parser(
        "learn", help="act on a `/codemop learn <why>` reply to one of CodeMop's comments",
        description=f"Act on a `/codemop learn <why>` reply to one of CodeMop's comments on a pull request: add a "
                    f"note to {LEARNED_FILE} on the PR's branch, resolve the conversation, and reply to confirm. "
                    "Needs a token with contents: write and pull-requests: write.",
    )
    learn.add_argument("target", help="owner/repo#123 or a pull request URL")
    learn.add_argument("--comment", type=int, required=True, metavar="ID", help="the reply's id")
    learn.add_argument("--github-api-url", default=DEFAULT_API_URL, help="for GitHub Enterprise Server")

    check = commands.add_parser(
        "check", help="update CodeMop's merge check on a pull request",
        description="Set CodeMop's merge check (a commit status, for repositories with `merge_check: true` in "
                    f"{CONFIG_FILE}) on a pull request's latest commit, from its summary and which of CodeMop's "
                    "conversations are resolved. Needs a token with statuses: write.",
    )
    check.add_argument("target", help="owner/repo#123 or a pull request URL")
    check.add_argument("--comment", type=int, metavar="ID",
                       help="the `/codemop check` comment that asked for it, to react to so its author knows it ran")
    check.add_argument("--github-api-url", default=DEFAULT_API_URL, help="for GitHub Enterprise Server")
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
    if report.already_dismissed:
        notes.append(f"Left out {report.already_dismissed} suggestion(s) dismissed earlier on this pull request")
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

    head_sha = summary = pull = full_diff = since = None
    state = SummaryState()
    if pr is None:
        diff, target = sys.stdin.read(), "stdin"
    else:
        target = str(pr)
        try:
            if args.post:
                # The commit the review's line numbers will refer to, read before the diff
                pull = await fetch_pull_request(pr, token=token, api_url=args.github_api_url)
                head_sha = pull.head_sha
                summary = find_summary(await list_issue_comments(pr, token=token, api_url=args.github_api_url))
                state = read_state(summary.body if summary else None)
                if state.commit == head_sha:
                    print(f"CodeMop has already reviewed {target} at {head_sha[:7]}; nothing to do")
                    return 0
            diff = full_diff = await fetch_pr_diff(pr, token=token, api_url=args.github_api_url)
            if args.post and state.kept and state.commit:
                # A re-review: just the commits since the last review, if it's an ancestor (not after a
                # force-push), and only in files the PR changes (not ones a merge of the base brought in)
                newer = await compare_commits(pr.repo, state.commit, head_sha, token=token, api_url=args.github_api_url)
                if newer is not None:
                    diff, since = only_files_in(newer, full_diff), state.commit
        except GitHubError as e:
            print(f"codemop: {e}", file=sys.stderr)
            return 1
    settled, threads = await load_settled(pr, token, args.github_api_url, dismissed=args.post)

    try:
        model = create_model(
            args.provider, args.model, base_url=args.base_url, api_key_env=args.api_key_env, effort=args.effort
        )
    except ValueError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 2

    gate = args.post and config.merge_check
    if gate:  # so the PR can't be merged while it's being reviewed
        await set_status(pr, head_sha, "pending", "Reviewing the latest changes", token, args.github_api_url)
    report = await review_diff(
        diff, model,
        chunk_tokens=args.chunk_tokens or config.chunk_tokens,
        min_confidence=args.min_confidence if args.min_confidence is not None else config.min_confidence,
        ignored_paths=[*DEFAULT_IGNORED_PATHS, *config.ignore, *(args.ignore or [])],
        max_changed_lines=args.max_changed_lines,
        settled=settled,
    )
    less_important = 0
    if args.post:
        # Comments can only go on lines in the PR's own diff (a re-review's diff may show others)
        placement = place_suggestions(report.suggestions, parse_diff(full_diff))
        report.unplaced += placement.unplaced
        report.suggestions = placement.placed
        if since:  # after the first review, only what matters
            important = [s for s in report.suggestions if s.severity in (Severity.bug, Severity.security)]
            less_important = len(report.suggestions) - len(important)
            report.suggestions = important
    print(report_json(report, target, config_source) if args.json else report_text(report, target, config_source))
    if args.post:
        if report.stopped:
            print(f"codemop: not posting a review: {report.stopped}", file=sys.stderr)
            if gate:
                await set_status(pr, head_sha, "error", f"Couldn't review: {report.stopped}", token, args.github_api_url)
            return 1
        try:
            # A fork's branch can't be committed to: no checklist, and no `/codemop learn` there
            same_repo = pull.head_repo == pr.repo
            url = await post(pr, pull, report, state, summary.id if summary else None, threads, full_diff,
                             token=token, api_url=args.github_api_url,
                             max_comments=args.max_comments or config.max_comments,
                             checklist=args.checklist and same_repo, teachable=same_repo,
                             since=since, less_important=less_important, merge_check=gate)
        except GitHubError as e:
            print(f"codemop: {e}", file=sys.stderr)
            if gate:
                await set_status(pr, head_sha, "error", f"Couldn't post the review: {e}", token, args.github_api_url)
            return 1
        print(f"Posted the review: {url}", file=sys.stderr if args.json else sys.stdout)
        if gate:
            result, description = merge_status(state, config.merge_check_confidence, report.too_large)
            if not await set_status(pr, head_sha, result, description, token, args.github_api_url, url):
                return 1
    # Too large to review is a deliberate limit, not a failure
    return 0 if report.complete or report.too_large else 1


def only_files_in(diff: str, pr_diff: str) -> str:
    """The parts of `diff` for files the pull request changes"""
    changed = {f.path for f in parse_diff(pr_diff)}
    parts = re.split(r"(?m)^(?=diff --git )", diff)
    return "".join(part for part in parts if part and any(f.path in changed for f in parse_diff(part)))


async def post(pr: PullRequestRef, pull: PullRequest, report: ReviewReport, state: SummaryState,
               summary_id: Optional[int], threads: List[ReviewThread], pr_diff: str, *, token: str, api_url: str,
               max_comments: int, checklist: bool, teachable: bool, since: Optional[str], less_important: int,
               merge_check: bool = False) -> str:
    """
    Bring the summary's findings up to date, post the new issues as a review, then create or
    update the summary comment, last, so it only says a commit was reviewed once everything is
    posted; then resolve the conversations of findings whose code has been fixed. Returns the
    summary's URL.
    """
    api = dict(token=token, api_url=api_url)
    head = pull.head_sha
    shown = {f.path: file_lines(f) for f in parse_diff(pr_diff)}
    ours = [t for t in threads if trusted(t.first_comment_by_bot, t.first_comment_association)
            and parse_comment(t.first_comment_body)]
    sync_threads(state, conversations(threads))
    paths = {f.path for f in state.open if f.found_in != head and f.original}
    head_files = {path: await fetch_repo_file(pull.head_repo, path, ref=head, **api) for path in paths}
    new, addressed = update_earlier(state, report.suggestions, head_files, shown, head)
    state.add(new, shown, head)
    state.commit = head

    inline = ranked(new)[:max_comments]
    review_url, rejected = None, False
    if inline:
        try:
            review_url = await post_review(pr, review_payload(inline, head, new), **api)
        except GitHubError as e:
            if e.status != 422:
                raise
            rejected = True  # the summary lists them all anyway
    options = dict(review_url=review_url, inline_rejected=rejected, checklist=checklist, teachable=teachable,
                   since=since, less_important=less_important, not_commented=len(new) - len(inline),
                   merge_check=merge_check)
    cost = format_cost(report.cost, report.usage)
    for finding in state.findings:
        if finding.status != OPEN:  # done: its fix and lines aren't needed any more
            finding.code = finding.original = None
    body = summary_body(state, report, cost, **options)
    # Too long for GitHub? Give up the open findings' fixes (their checkboxes), and only then
    # their lines (which tell later reviews whether they've been addressed)
    for drop in ("code", "original"):
        if len(body) <= MAX_COMMENT_CHARS:
            break
        for finding in state.open:
            setattr(finding, drop, None)
        body = summary_body(state, report, cost, **options)
    try:
        url = await post_issue_comment(pr, body, comment_id=summary_id, **api)
    except GitHubError as e:
        if summary_id is None or e.status != 404:
            raise
        url = await post_issue_comment(pr, body, **api)  # it was deleted meanwhile

    for finding in addressed:
        thread = next((t for t in ours if not t.resolved and t.path == finding.path
                       and parse_comment(t.first_comment_body)[1] == finding.title), None)
        if thread:
            await resolve_thread(thread.id, **api)
    return url


def conversations(threads: List[ReviewThread]) -> List[Tuple[str, str, bool]]:
    """(path, title, resolved) for each of the threads CodeMop started"""
    found = []
    for t in threads:
        parsed = parse_comment(t.first_comment_body) if trusted(t.first_comment_by_bot, t.first_comment_association) else None
        if parsed:
            found.append((t.path, parsed[1], t.resolved))
    return found


async def set_status(pr: PullRequestRef, sha: str, state: str, description: str, token: str, api_url: str,
                     target_url: Optional[str] = None) -> bool:
    """Set the merge check's status; whether that worked (it's said why, if not)"""
    try:
        await set_commit_status(pr.repo, sha, state, description, target_url=target_url, token=token, api_url=api_url)
        return True
    except GitHubError as e:
        print(f"codemop: couldn't set the merge check: {e}", file=sys.stderr)
        return False


async def repo_settings(pr: PullRequestRef, token: str, api_url: str) -> RepoConfig:
    """The repository's .codemop.yml from its default branch (the defaults if it's missing or broken)"""
    text = await fetch_repo_file(pr.repo, CONFIG_FILE, token=token, api_url=api_url)
    try:
        return parse_config(text, source=f"{pr.repo}/{CONFIG_FILE}") if text else RepoConfig()
    except ConfigError as e:
        print(f"codemop: using the default settings: {e}", file=sys.stderr)
        return RepoConfig()


NOT_REVIEWED = ("The latest commit hasn't been reviewed yet, so the merge check stays as it is. It's updated when "
                "the review of that commit finishes; comment `/codemop check` again after that if you need to.")


async def check_after_change(pr: PullRequestRef, sha: str, api: dict) -> Optional[str]:
    """
    After a change that doesn't get a review (CodeMop's own commit, or a conversation resolved),
    set the merge check on `sha` from the summary and the conversations as they are now. Only
    on the commit the summary describes: anything else hasn't been reviewed, and setting the
    check there would let it pass unreviewed code. Returns why it wasn't set, if that matters.
    """
    config = await repo_settings(pr, **api)
    if not config.merge_check:
        return None
    summary = find_summary(await list_issue_comments(pr, **api))
    state = read_state(summary.body if summary else None)
    if not state.kept:
        return None  # not reviewed yet: the review will set it
    if state.commit != sha:
        return NOT_REVIEWED
    sync_threads(state, conversations(await list_review_threads(pr, **api)))
    result, description = merge_status(state, config.merge_check_confidence)
    return None if await set_status(pr, sha, result, description, **api) else "couldn't set the merge check"


async def record_commit(pr: PullRequestRef, parent: str, commit: str, api: dict) -> None:
    """After CodeMop's own commit on `parent`: record it as reviewed if it can be, then set the merge check on it"""
    summary = find_summary(await list_issue_comments(pr, **api))
    body = record_own_commit(summary.body, parent, commit) if summary else None
    if body:
        await post_issue_comment(pr, body, comment_id=summary.id, **api)
    why = await check_after_change(pr, commit, api)
    if why:
        print(f"Merge check not updated: {why}")


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
    api = dict(token=token, api_url=args.github_api_url)
    try:
        pull = await fetch_pull_request(pr, **api)
        why = await check_after_change(pr, pull.head_sha, api)
        if why == NOT_REVIEWED and args.comment:
            await post_issue_comment(pr, why, **api)  # say why nothing changed, rather than leave them guessing
        elif args.comment and not why:
            await react_to_issue_comment(pr.repo, args.comment, "+1", **api)
        print(why or "Merge check updated")
        return 1 if why and why != NOT_REVIEWED else 0
    except GitHubError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 1


async def load_settled(pr: Optional[PullRequestRef], token: Optional[str], api_url: str,
                       dismissed: bool) -> Tuple[Settled, List[ReviewThread]]:
    """
    What not to raise again: the repository's learned notes (from its default branch, or for a
    local diff the current directory), and with `dismissed` the CodeMop comments resolved on the
    PR. Also the PR's review threads (with `dismissed`), for the summary to bring up to date.
    """
    if pr is None:
        path = Path(LEARNED_FILE)
        return Settled(learned=parse_learned(path.read_text() if path.is_file() else None)), []
    try:
        learned = parse_learned(await fetch_repo_file(pr.repo, LEARNED_FILE, token=token, api_url=api_url))
        threads = await list_review_threads(pr, token=token, api_url=api_url) if dismissed else []
    except GitHubError as e:
        # Not worth failing the review over: it may just raise something again
        print(f"codemop: couldn't read what's been dismissed or learned ({e}); reviewing without it", file=sys.stderr)
        return Settled(), []
    resolved = []
    for thread in threads:
        is_codemops = trusted(thread.first_comment_by_bot, thread.first_comment_association)
        parsed = parse_comment(thread.first_comment_body) if thread.resolved and is_codemops else None
        if parsed:
            resolved.append(Dismissed(thread.path, thread.line, parsed[0], parsed[1]))
    return Settled(learned=learned, dismissed=resolved), threads


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
    api = dict(token=token, api_url=args.github_api_url)

    async def reply(text: str) -> None:
        await reply_to_review_comment(pr, args.comment, text, **api)
        print(text)

    try:
        # The reply and what it replies to, read from GitHub (not trusted from the event)
        command = await fetch_review_comment(pr.repo, args.comment, **api)
        parent = await fetch_review_comment(pr.repo, command.in_reply_to, **api) if command and command.in_reply_to else None
        parsed = parse_comment(parent.body) if parent and trusted(parent.author_is_bot, parent.author_association) else None
        if not command or not command.body.strip().startswith(LEARN_COMMAND) or not parsed:
            print("Not a `/codemop learn` reply to one of CodeMop's comments; nothing to do")
            return 0
        reason = command.body.strip()[len(LEARN_COMMAND):].strip()
        if not reason:
            await reply(f"Say why it's fine, so the note makes sense to the next person: `{LEARN_COMMAND} <why it's fine>`.")
            return 0
        if await user_permission(pr.repo, command.author, **api) not in WRITE_PERMISSIONS:
            await reply(f"Only people with write access to {pr.repo} can teach CodeMop. Resolving this conversation "
                        "dismisses it for this pull request.")
            return 0

        entry = Learned(parent.path, parsed[1], reason, f"#{pr.number}, @{command.author}")
        thread = next((t for t in await list_review_threads(pr, **api) if t.first_comment_id == parent.id), None)
        pull = await fetch_pull_request(pr, **api)
        if pull.head_repo != pr.repo:
            if thread:
                await resolve_thread(thread.id, **api)
            await reply("I can't commit to a fork's branch, so I've only resolved this conversation (I won't raise it "
                        f"again on this PR). To teach the whole repository, add this to `{LEARNED_FILE}` on the "
                        f"default branch:\n\n```yaml\n{learned_yaml(entry).strip()}\n```")
            return 0

        for attempt in range(2):  # again if the branch moves on while this runs
            pull = await fetch_pull_request(pr, **api)
            text = await fetch_repo_file(pull.head_repo, LEARNED_FILE, ref=pull.head_sha, **api)
            message = f"Teach CodeMop: {entry.issue}\n\n{entry.reason}\n\nFrom @{command.author} on #{pr.number}."
            try:
                commit = await commit_files(pull.head_repo, pull.head_ref, pull.head_sha,
                                            {LEARNED_FILE: add_learned(text, entry)}, message, **api)
                break
            except GitHubError as e:
                if e.status != 422 or attempt:
                    raise
        if thread:
            await resolve_thread(thread.id, **api)
        await record_commit(pr, pull.head_sha, commit, api)  # no review runs on CodeMop's own commit
        await reply(f"Learned: I've added this to `{LEARNED_FILE}` on this branch ({commit[:7]}) and resolved this "
                    "conversation. Once this PR is merged, I won't raise it again in this repository. If that's too "
                    "broad, edit or delete the note in that file.")
    except GitHubError as e:
        print(f"codemop: {e}", file=sys.stderr)
        return 1
    return 0


WRITE_PERMISSIONS = {"admin", "maintain", "write"}
MAX_COMMENT_CHARS = 65_000  # GitHub's limit is 65,536


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
    api = dict(token=token, api_url=args.github_api_url)
    try:
        if args.by and await user_permission(pr.repo, args.by, **api) not in WRITE_PERMISSIONS:
            print(f"Not applying fixes for {args.by}: only people with write access to {pr.repo} can")
            return 0
        summary = find_summary(await list_issue_comments(pr, **api))
        fixes = stored_fixes(summary.body) if summary else {}
        wanted = [fixes[i] for i in sorted(ticked(summary.body)) if i in fixes] if summary else []
        if not wanted:
            print(f"No ticked fixes to apply on {pr}")
            return 0

        for attempt in range(2):  # again if the branch moves on while this runs
            pull = await fetch_pull_request(pr, **api)
            if pull.head_repo != pr.repo:
                print(f"Can't commit to {pr}'s branch: it's in a fork ({pull.head_repo})")
                return 0
            files, applied, skipped = await _apply_to_files(pull, wanted, api)
            commit = pull.head_sha
            if not files:
                break
            message = "Apply CodeMop's suggested fixes\n\n" + "\n".join(f"- {f.path}:{f.line}: {f.title}" for f in applied)
            if args.by:
                message += f"\n\nTicked by @{args.by} in CodeMop's summary on #{pr.number}."
            try:
                commit = await commit_files(pull.head_repo, pull.head_ref, pull.head_sha, files, message, **api)
                break
            except GitHubError as e:
                if e.status != 422 or attempt:
                    raise

        # Mark the summary as it is now, not as it was read: more boxes may have been ticked meanwhile
        # (they stay ticked, for the next run), or a newer review may have updated it (findings keep
        # their ids, so the marks still go on the right ones)
        latest = find_summary(await list_issue_comments(pr, **api)) or summary
        await post_issue_comment(pr, record_applied(latest.body, commit, applied, skipped), comment_id=latest.id, **api)
        if applied:
            await record_commit(pr, pull.head_sha, commit, api)  # no review runs on CodeMop's own commit
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


async def _apply_to_files(pull: PullRequest, wanted, api: dict):
    """The new text of each file the fixes change, and which fixes were applied and skipped"""
    files, applied, skipped = {}, [], []
    for path in dict.fromkeys(f.path for f in wanted):
        for_path = [f for f in wanted if f.path == path]
        text = await fetch_repo_file(pull.head_repo, path, ref=pull.head_sha, **api)
        if text is None:
            skipped += [(f, "the file no longer exists") for f in for_path]
            continue
        result = apply_fixes(text, for_path)
        applied += result.applied
        skipped += result.skipped
        if result.applied:
            files[path] = result.text
    return files, applied, skipped


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "review":
        return asyncio.run(run_review(args))
    if args.command == "apply":
        return asyncio.run(run_apply(args))
    if args.command == "learn":
        return asyncio.run(run_learn(args))
    if args.command == "check":
        return asyncio.run(run_check(args))
    return 2


if __name__ == "__main__":
    sys.exit(main())
