# Review eval

Compares models on the same 36 pull request diffs, each with a hand-written answer key, by running
CodeMop's real review pipeline and grading every comment. It chose the default model, and can be
rerun when the prompt or the models change.

- [`cases.yml`](cases.yml): the cases and their known issues; the diffs are in `cases/`, and
  [`CASES.md`](CASES.md) shows them together (`render_cases.py`). 9 are real bugs from CodeMop's own
  history, 9 have a seeded bug, 8 have a seeded bug that only shows in other files (`cross-file`, with
  the repository in `repos/`; 3 of them in TypeScript or JavaScript), 10 are clean (3 of them
  cross-file); 15 are tagged simple and 21 complex
- [`run.py`](run.py): reviews every case with one configuration and grades it. A comment counts as
  finding a known issue when it's within 3 lines of it and a judge model (Claude Opus 4.8, not one of
  those compared) agrees it describes that issue and its claims hold up. Any other comment is judged
  another real issue or a false alarm. A buggy case passes when every major issue is found; a clean
  case passes when there are no false alarms
- [`test_grading.py`](test_grading.py) checks the grading with no API calls (a perfect review passes
  every case; an empty one only the clean cases); [`judge_checks.py`](judge_checks.py) checks the
  judge rejects comments that are deliberately wrong

```bash
pip install -e . pytest
pytest evals/review/test_grading.py
export ANTHROPIC_API_KEY=...                       # spends money: about $2 a configuration
python evals/review/run.py --variant baseline      # every case, twice; resumes if interrupted
python evals/review/summarise.py                   # the comparison table
python evals/review/review_judgements.py baseline  # every comment with the judge's verdict
```

Results go to `.claude/hillclimb/review/` (not committed). `--rejudge` grades saved reviews again
after a judge change; `--regrade` does so from the saved verdicts after an answer-key change, with no
API calls.

## Results, 2026-10-08

Each configuration reviewed every case twice (50 reviews). List prices as of 2026-09-25.

| | Opus 5.5, high effort (default) | Opus 5.5, low | Sonnet 5.5, high | Sonnet 5.5, low | Haiku 4.5 |
|---|---|---|---|---|---|
| Cases passed (95% CI) | **47/50** (84–98%) | 44/50 (76–94%) | 44/50 (76–94%) | 45/50 (79–96%) | 32/50 (50–76%) |
| Simple cases | 30/30 | 30/30 | 30/30 | 30/30 | 27/30 |
| Complex cases | **17/20** | 14/20 | 14/20 | 15/20 | 5/20 |
| Major issues found | **37/40** | 34/40 | 34/40 | 35/40 | 26/40 |
| Minor issues found | 7/16 | 6/16 | **11/16** | 6/16 | 2/16 |
| Other real issues raised | 34 | 24 | 41 | 27 | 13 |
| False alarms | 1 | 1 | 4 | 2 | 43 |
| Comments that were right | 99% | 98% | 96% | 97% | 51% |
| Review cost per case | $0.023 | $0.016 | $0.011 | $0.009 | $0.004 |
| Median latency | 5s | 3s | 4s | 3s | 3s |

- **The default stays Claude Opus 5.5 at high effort.** It did best on the complex changes, and a
  review still costs about two cents at these sizes
- On simple changes, every Opus and Sonnet configuration found everything, so Sonnet 5.5 at low
  effort (about 40% of the cost) gives up nothing there. Routing reviews by complexity would save
  about a cent per review, at the risk of missing more on changes that look simple and aren't, so
  it isn't worth building yet
- Haiku 4.5 isn't reliable enough to review: half its comments were wrong, often at high
  confidence, and it flagged clean code in half the clean cases
- Limits: 25 small cases, so the differences between the Opus and Sonnet configurations are within
  the margin of error. In `real-ai-analysis`, two known issues are on the same line and the judge
  credits a comment with only one, so no configuration can pass it even when a comment names both
  (it affects every configuration equally). Mistral and local models weren't compared

## Grouping, 2026-10-09

The instructions gained `group` (related problems marked so one checklist item fixes them
all). The default, Opus 5.5 at high effort, again reviewed every case twice:

| | Before | With grouping |
|---|---|---|
| Cases passed | 47/50 | 47/50 |
| Major issues found | 37/40 | 37/40 |
| False alarms | 1 | 1 |
| Minor issues found | 7/16 | 4/16 |
| Other real issues raised | 34 | 28 |
| Review cost per case | $0.023 | $0.024 |

What decides a pass held exactly. Fewer extras were raised (minor and other real issues),
which may be noise at this size; worth watching. The model grouped sparingly and where it
fits: the undefined `pr_data` used in two places, and the backup command injection, whose
fix needs both the regex anchored and `shell=True` dropped.

## Repository context, 2026-10-09

The same default with repository context: the whole of each changed function, and the
definitions the change uses (in the same file, or imported from the repository), read at the
case's commit with git. Only the cases from this repository's history can have any; the seeded
and synthetic ones are self-contained.

| | Without context | With context |
|---|---|---|
| Cases passed | 47/50 | 44/50 |
| Complex cases | 17/20 | 14/20 |
| Major issues found | 37/40 | 34/40 |
| Minor issues found | 4/16 | 8/16 |
| False alarms | 1 | 2 |
| Review cost per case | $0.024 | $0.026 |

No measurable gain; the differences look like noise. One of the three cases that changed
(real-pr-model) got no context at all, so the same input passed once less; in another
(real-security-config) the model found the issue with context but rated it 0.45, just under
the 0.5 threshold. Why so little: most of the real cases are commits that created whole
files, so the diff already shows everything the context would add, and what they lack is in
other files that call the changed code (where `github_id` is set to the PR number, for
real-pr-model), which this version doesn't look for.

## Where the changed code is used, 2026-10-09

Context now also includes where what the change defines is used: the functions that call a
changed function, or use a changed constant or field, in files that import it. Seven
cross-file cases were added for it: in five, the change is fine on its own and breaks code in
another file (arguments reordered, None returned instead of an exception, seconds instead of
minutes, a function made async, a dict key renamed); two are clean changes that only look
risky (a new optional argument, a list returned as a generator). The default with context and
uses, against the default without context (the grouping run above, plus the new cases), every
case twice:

| | Without context | With context and uses |
|---|---|---|
| Cases passed | 55/64 | **59/64** |
| Cases that got context (16) | 24/32 | **29/32** |
| Cases that didn't (16; the same input both times) | 31/32 | 30/32 |
| Cross-file bugs found | 4/10 | **10/10** |
| False alarms | 1 | 1 |
| Review cost per case | $0.022 | $0.025 |

- **Context is now on by default.** The three cross-file bugs a diff gives no hint of
  (arguments reordered, units changed, made async) went from 0/6 to 6/6, the clean cross-file
  cases stayed clean, and a review costs about 13% more
- The difference on the cases without context is noise: their input was identical
- To watch: real-security-config passed once in two runs with context, in both context
  configurations so far, against every run without it. Its context includes four uses of the
  changed settings; a larger sample would say whether they distract
- Limits: the cross-file cases were written for this, so they show what context can do rather
  than how often real PRs need it; dogfooding will say more


## Where a problem shows up outside the diff, 2026-10-10

Two changes, found while dogfooding and by the eval:

- **The context is numbered like the diff, and a finding can say where it shows up outside the
  diff** (`outside_diff`: a caller the change breaks, a reference it makes wrong). The comment
  still goes on the changed lines; the finding remembers both places, and changing either
  counts as addressing it. (On PR #23 the stale line was outside the diff, so fixing it didn't
  count.) The model used it in every cross-file case, each time pointing at the caller.
- **Context never repeats code the diff shows.** Code added in one file was coming back, as
  "unchanged" context, as a definition another file imports. In real-security-config that was
  the CORS settings, and the model stopped mentioning the wildcard-with-credentials bug in them
  (it had passed 2 of 6 runs with context, against 4 of 4 without).

On the 16 cases that get context (the other 16 have the same input whatever the configuration),
each twice:

| | Without context | Context | Numbered, with outside_diff | **And without the diff's code** |
|---|---|---|---|---|
| Cases passed | 24/32 | 29/32 | 27/31 | **29/32** |
| real-security-config | 2/2 | 1/2 | 0/2 | 1/2 |

With the fix the model raises the CORS bug in both runs again, once at 0.40, just under the 0.5
threshold: back to the same borderline it had without context. real-ai-analysis fails in every
configuration (see the limits above). No new false alarms; about 2.6¢ a review.

## TypeScript and JavaScript, 2026-10-10

Context now reads TypeScript and JavaScript too (with tree-sitter), so their changes get the
same context as Python's: the function around each change, where the changed code is used in
files that import it (through relative paths or aliases like `@/lib/…`), and definitions it
uses. Four cases were added, with bugs a TypeScript compiler doesn't catch: a constant changed
from minutes to seconds, a sort order reversed under a caller that takes the first result, a
function made async under a JSX caller that doesn't await it, and a clean change (an optional
prop) that only looks risky. Each twice, with the current instructions:

| | With context | Without |
|---|---|---|
| The two TypeScript bugs | **4/4** | 0/4 (not mentioned) |
| The JavaScript bug | 2/2 | 2/2 (the diff shows `async`) |
| The clean change | 2/2, no false alarms | 2/2 |

The Python cases' context is unchanged (checked against the previous version, case by case).

