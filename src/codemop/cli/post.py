"""
codemop review --post: review a pull request and post the review on it, updating the summary
it keeps there. A commit already reviewed isn't reviewed again; a later commit is reviewed
from the last one reviewed (re-reviews: just what's new, only bugs and security issues).
"""
import asyncio
import re
import sys
from typing import List, Optional, Sequence

from codemop.cli.common import conversations, set_status, thread_states
from codemop.cli.report import format_cost
from codemop.cli.review import fetch_diff_and_learned, print_report, review
from codemop.config import RepoConfig
from codemop.github import api
from codemop.github.api import GitHubError, IssueComment, PullRequest, PullRequestRef, ReviewThread
from codemop.github.check import merge_status
from codemop.github.files import GitHubFiles
from codemop.github.review import ranked, review_payload
from codemop.github.summary import (
    SummaryState, find_summary, read_state, summary_body, sync_threads, update_earlier,
)
from codemop.providers.base import ReviewModel
from codemop.review.diff import FileDiff, parse_diff
from codemop.review.learned import Dismissed, Settled
from codemop.review.pipeline import ReviewReport
from codemop.review.placement import place_suggestions
from codemop.review.schema import IMPORTANT_SEVERITIES


async def review_and_post(args, pr: PullRequestRef, auth: dict, model: ReviewModel, config: RepoConfig,
                          config_source: str) -> int:
    # The commit the review's line numbers will refer to, read before the diff
    pull, comments = await asyncio.gather(api.fetch_pull_request(pr, **auth), api.list_issue_comments(pr, **auth))
    summary = find_summary(comments)
    state = read_state(summary.body if summary else None)
    if state.commit == pull.head_sha:
        print(f"CodeMop has already reviewed {pr} at {pull.head_sha[:7]}; nothing to do")
        return 0
    (full_diff, learned), threads = await asyncio.gather(fetch_diff_and_learned(pr, auth), review_threads(pr, auth))
    files = parse_diff(full_diff)
    diff, since = full_diff, None
    if state.commit:
        # A re-review: just the commits since the last review, if it's an ancestor (not after a
        # force-push), and only in files the PR changes (not ones a merge of the base brought in)
        newer = await api.compare_commits(pr.repo, state.commit, pull.head_sha, **auth)
        if newer is not None:
            diff, since = only_files_in(newer, files), state.commit

    # Resolved conversations dismiss their findings, and the model is told those are settled
    sync_threads(state, thread_states(threads))
    dismissed = [Dismissed(t.path, t.line, c.severity, c.title) for c, t in conversations(threads) if t.resolved]

    async def status(result: str, description: str, url: Optional[str] = None) -> bool:
        return not config.merge_check or await set_status(pr, pull.head_sha, result, description, auth, url)

    await status("pending", "Reviewing the latest changes")  # so the PR can't be merged mid-review
    context = GitHubFiles(pull.head_repo or pr.repo, pull.head_sha, **auth) if args.context else None
    report = await review(args, config, model, diff, Settled(learned=learned, dismissed=dismissed), context)

    less_important = 0
    if since:  # comments can only go on lines in the PR's own diff, and after the first review, only what matters
        placement = place_suggestions(report.suggestions, files)
        report.unplaced += placement.unplaced
        important = [s for s in placement.placed if s.severity in IMPORTANT_SEVERITIES]
        less_important = len(placement.placed) - len(important)
        report.suggestions = important
    code = print_report(args, report, str(pr), config_source)
    if report.stopped:
        print(f"codemop: not posting a review: {report.stopped}", file=sys.stderr)
        await status("error", f"Couldn't review: {report.stopped}")
        return 1
    try:
        url = await post(pr, pull, report, state, summary, threads, files, auth, diff if since else None,
                         max_comments=args.max_comments or config.max_comments, checklist=args.checklist,
                         since=since, less_important=less_important, merge_check=config.merge_check)
    except GitHubError as e:
        await status("error", f"Couldn't post the review: {e}")
        raise
    print(f"Posted the review: {url}", file=sys.stderr if args.json else sys.stdout)
    result, description = merge_status(state, config.merge_check_confidence, report.too_large)
    return code if await status(result, description, url) else 1


async def review_threads(pr: PullRequestRef, auth: dict) -> List[ReviewThread]:
    try:
        return await api.list_review_threads(pr, **auth)
    except GitHubError as e:  # not worth failing the review over: it may just raise something again
        print(f"codemop: couldn't read which conversations are resolved ({e}); reviewing without it", file=sys.stderr)
        return []


def only_files_in(diff: str, pr_files: Sequence[FileDiff]) -> str:
    """The parts of `diff` for files the pull request changes"""
    changed = {f.path for f in pr_files}
    parts = re.split(r"(?m)^(?=diff --git )", diff)
    return "".join(part for part in parts if part and any(f.path in changed for f in parse_diff(part)))


async def post(pr: PullRequestRef, pull: PullRequest, report: ReviewReport, state: SummaryState,
               summary: Optional[IssueComment], threads: Sequence[ReviewThread], files: Sequence[FileDiff],
               auth: dict, reviewed_diff: Optional[str], *, max_comments: int, checklist: bool, since: Optional[str],
               less_important: int, merge_check: bool) -> str:
    """
    Bring the summary's findings up to date, post the new issues as a review, then create or
    update the summary comment, last, so it only says a commit was reviewed once everything is
    posted; then resolve the conversations of findings whose code has been fixed. Returns the
    summary's URL. (`reviewed_diff`: a re-review's diff, so only its files are re-read.)
    """
    head = pull.head_sha
    shown = {f.path: f.new_lines() for f in files}
    # An earlier finding can only have been addressed in a file that's changed since it was found
    changed = {f.path for f in parse_diff(reviewed_diff)} if reviewed_diff is not None else None
    paths = sorted({f.path for f in state.open if f.found_in != head and f.original
                    and (changed is None or f.path in changed)})
    texts = await asyncio.gather(*(api.fetch_repo_file(pull.head_repo, path, ref=head, **auth) for path in paths))
    new, addressed = update_earlier(state, report.suggestions, dict(zip(paths, texts)), shown, head)
    added = state.add(new, shown, head)
    state.commit = head

    inline = ranked(new)[:max_comments]  # most important first, in the same order as `added`
    review_url, rejected = None, False
    if inline:
        try:
            review_url = await api.post_review(
                pr, review_payload(inline, head, new, [f.id for f in added[:max_comments]]), **auth)
        except GitHubError as e:
            if e.status != 422:
                raise
            rejected = True  # the summary lists them all anyway
    same_repo = pull.head_repo == pr.repo  # a fork's branch can't be committed to: no checklist or learning there
    body = summary_body(state, report, format_cost(report.cost, report.usage), review_url=review_url,
                        inline_rejected=rejected, checklist=checklist and same_repo, teachable=same_repo, since=since,
                        less_important=less_important, not_commented=len(new) - len(inline), merge_check=merge_check)
    try:
        url = await api.post_issue_comment(pr, body, comment_id=summary.id if summary else None, **auth)
    except GitHubError as e:
        if summary is None or e.status != 404:
            raise
        url = await api.post_issue_comment(pr, body, **auth)  # it was deleted meanwhile

    by_finding = {c.finding_id: t for c, t in conversations(threads) if c.finding_id is not None}
    by_title = {(t.path, c.title): t for c, t in conversations(threads)}
    to_resolve = [by_finding.get(f.id) or by_title.get((f.path, f.title)) for f in addressed]
    await asyncio.gather(*(api.resolve_thread(t.id, **auth) for t in to_resolve if t and not t.resolved))
    return url
