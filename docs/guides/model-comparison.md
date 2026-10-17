# Which model reviews code best? We measured

Every AI code reviewer says it catches bugs. We wanted numbers, so before choosing CodeMop's
default model we built an eval: real and seeded bugs, clean changes that should get no
comments, and a grader that checks every comment against an answer key. Here's what it found.

## How it works

- **The cases:** pull request diffs, each with a hand-written answer key of the issues in it.
  Some are real bugs from CodeMop's own history, some have a bug seeded in, some are clean
  changes, and some have a bug that only shows in another file (the change is fine on its own,
  and breaks the code that calls it)
- **The review:** each model reviews each case through CodeMop's real pipeline, twice
- **The grading:** a comment counts as finding a known issue when it's on the right lines and a
  judge model (Claude Opus 4.8, not one of the models compared) agrees it describes that issue
  and its claims hold up. Any other comment is judged a real issue nobody listed, or a false
  alarm. A case passes when every major issue is found, or, for a clean case, when nothing is
  flagged

The cases, the grader and every result are in the
[eval's folder](../../evals/review/README.md), so you can rerun it.

## The results

25 cases, each reviewed twice (50 reviews per model), October 2026, at list prices.

| | Claude Opus 5.5, high effort | Opus 5.5, low | Sonnet 5.5, high | Sonnet 5.5, low | Haiku 4.5 |
|---|---|---|---|---|---|
| Cases passed | **47/50** | 44/50 | 44/50 | 45/50 | 32/50 |
| Simple changes | 30/30 | 30/30 | 30/30 | 30/30 | 27/30 |
| Complex changes | **17/20** | 14/20 | 14/20 | 15/20 | 5/20 |
| Major issues found | **37/40** | 34/40 | 34/40 | 35/40 | 26/40 |
| False alarms | **1** | 1 | 4 | 2 | 43 |
| Comments that were right | **99%** | 98% | 96% | 97% | 51% |
| Cost per review | $0.023 | $0.016 | $0.011 | $0.009 | $0.004 |
| Median time | 5s | 3s | 4s | 3s | 3s |

- **On simple changes, every Opus and Sonnet configuration found everything.** The differences
  are all in the complex ones, where Opus at high effort found the most
- **False alarms matter more than they look.** A reviewer that's wrong half the time teaches
  people to ignore it. Haiku 4.5 raised 43 false alarms, often sure of itself, and flagged clean
  code in half the clean cases
- **A good review is cheap.** The best configuration cost about two cents a review. Saving a cent
  by routing simple changes to a smaller model isn't worth the risk of a change that looks
  simple and isn't

So CodeMop's default is Claude Opus 5.5 at high effort. You can choose
[any model](../../README.md#choosing-a-model), including a local one.

## Reading the code around the change

Most AI reviewers read only the diff. But a change can be right in itself and break what calls
it: arguments reordered, a value changed from minutes to seconds, a function made async. We
added cases like that, and compared the same model with and without the code around each change
(the whole function, and where the changed code is used in other files):

| | Diff only | With the code around it |
|---|---|---|
| Bugs that only show in another file | 4/10 | **10/10** |
| False alarms | 1 | 1 |
| Cost per review | $0.022 | $0.025 |

The bugs a diff gives no hint of went from 0 of 6 found to 6 of 6, for about 13% more per
review, so it's on by default, for Python, TypeScript and JavaScript.

## The limits

- 25 to 36 cases is small: the gaps between the Opus and Sonnet configurations are within the
  margin of error, and only the big ones (Haiku, and context on cross-file bugs) are clear
- The cross-file cases were written to test this, so they show what context can do, not how
  often real pull requests need it
- Models other than Claude's (Mistral, OpenAI, local models) weren't compared yet

The eval runs again whenever the review changes, and the [eval's folder](../../evals/review/README.md)
has every run since.
