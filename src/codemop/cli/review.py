"""codemop review: review a pull request or a diff, print the report, and with --post post it."""
import dataclasses
import json
import re
import sys
import textwrap
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from codemop import providers
from codemop.cli.common import (
    MAX_COMMENT_CHARS,
    conversations,
    github_token,
    set_status,
)
from codemop.config import (
    CONFIG_FILE,
    ConfigError,
    RepoConfig,
    load_config_file,
    parse_config,
)
from codemop.github import api
from codemop.github.api import (
    GitHubError,
    PullRequest,
    PullRequestRef,
    ReviewThread,
    parse_pr_reference,
)
from codemop.github.check import merge_status
from codemop.github.files import GitHubFiles
from codemop.github.review import parse_comment, ranked, review_payload
from codemop.github.summary import (
    OPEN,
    SummaryState,
    find_summary,
    read_state,
    summary_body,
    sync_threads,
    trusted,
    update_earlier,
)
from codemop.providers.base import Usage
from codemop.providers.pricing import PRICES_AS_OF
from codemop.review.chunks import DEFAULT_IGNORED_PATHS
from codemop.review.context import LocalFiles
from codemop.review.diff import parse_diff
from codemop.review.fixes import file_lines
from codemop.review.learned import (
    LEARNED_FILE,
    Dismissed,
    Settled,
    parse_learned,
)
from codemop.review.pipeline import ReviewReport, review_diff
from codemop.review.placement import place_suggestions
from codemop.review.schema import Severity


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
    text = await api.fetch_repo_file(pr.repo, CONFIG_FILE, token=token, api_url=args.github_api_url)
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
                pull = await api.fetch_pull_request(pr, token=token, api_url=args.github_api_url)
                head_sha = pull.head_sha
                summary = find_summary(await api.list_issue_comments(pr, token=token, api_url=args.github_api_url))
                state = read_state(summary.body if summary else None)
                if state.commit == head_sha:
                    print(f"CodeMop has already reviewed {target} at {head_sha[:7]}; nothing to do")
                    return 0
            diff = full_diff = await api.fetch_pr_diff(pr, token=token, api_url=args.github_api_url)
            if pull is None and args.context:  # its files, for context
                pull = await api.fetch_pull_request(pr, token=token, api_url=args.github_api_url)
            if args.post and state.kept and state.commit:
                # A re-review: just the commits since the last review, if it's an ancestor (not after a
                # force-push), and only in files the PR changes (not ones a merge of the base brought in)
                newer = await api.compare_commits(pr.repo, state.commit, head_sha, token=token, api_url=args.github_api_url)
                if newer is not None:
                    diff, since = only_files_in(newer, full_diff), state.commit
        except GitHubError as e:
            print(f"codemop: {e}", file=sys.stderr)
            return 1
    settled, threads = await load_settled(pr, token, args.github_api_url, dismissed=args.post)

    try:
        model = providers.create_model(
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
        context=None if not args.context else (
            LocalFiles(Path.cwd()) if pr is None
            else GitHubFiles(pull.head_repo or pr.repo, pull.head_sha, token=token, api_url=args.github_api_url)
        ),
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
    auth = dict(token=token, api_url=api_url)
    head = pull.head_sha
    shown = {f.path: file_lines(f) for f in parse_diff(pr_diff)}
    ours = [t for t in threads if trusted(t.first_comment_by_bot, t.first_comment_association)
            and parse_comment(t.first_comment_body)]
    sync_threads(state, conversations(threads))
    paths = {f.path for f in state.open if f.found_in != head and f.original}
    head_files = {path: await api.fetch_repo_file(pull.head_repo, path, ref=head, **auth) for path in paths}
    new, addressed = update_earlier(state, report.suggestions, head_files, shown, head)
    state.add(new, shown, head)
    state.commit = head

    inline = ranked(new)[:max_comments]
    review_url, rejected = None, False
    if inline:
        try:
            review_url = await api.post_review(pr, review_payload(inline, head, new), **auth)
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
        url = await api.post_issue_comment(pr, body, comment_id=summary_id, **auth)
    except GitHubError as e:
        if summary_id is None or e.status != 404:
            raise
        url = await api.post_issue_comment(pr, body, **auth)  # it was deleted meanwhile

    for finding in addressed:
        thread = next((t for t in ours if not t.resolved and t.path == finding.path
                       and parse_comment(t.first_comment_body)[1] == finding.title), None)
        if thread:
            await api.resolve_thread(thread.id, **auth)
    return url

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
        learned = parse_learned(await api.fetch_repo_file(pr.repo, LEARNED_FILE, token=token, api_url=api_url))
        threads = await api.list_review_threads(pr, token=token, api_url=api_url) if dismissed else []
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
