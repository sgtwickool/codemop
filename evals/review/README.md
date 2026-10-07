# Review eval

Compares models on the same 25 pull request diffs, each with a hand-written answer key, by running
CodeMop's real review pipeline and grading every comment. It chose the default model, and can be
rerun when the prompt or the models change.

- [`cases.yml`](cases.yml): the cases and their known issues; the diffs are in `cases/`, and
  [`CASES.md`](CASES.md) shows them together (`render_cases.py`). 9 are real bugs from CodeMop's own
  history, 9 have a seeded bug, 7 are clean; 15 are tagged simple and 10 complex
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
