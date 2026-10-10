# CodeMop

AI code review for pull requests, with the model of your choice. Tick the fixes you want and
it commits them. **[codemop.com](https://codemop.com)**

[![CI](https://github.com/sgtwickool/codemop/actions/workflows/ci.yml/badge.svg)](https://github.com/sgtwickool/codemop/actions/workflows/ci.yml)
[![Security scan](https://github.com/sgtwickool/codemop/actions/workflows/security.yml/badge.svg)](https://github.com/sgtwickool/codemop/actions/workflows/security.yml)
[![PyPI](https://img.shields.io/pypi/v/codemop)](https://pypi.org/project/codemop/)

- **Reviews every pull request, including ones from forks, safely.** It reads the diff and
  the repository through the API and never checks out or runs the PR's code, so it can hold
  your key on a stranger's PR
- **Fixes, not just findings.** Each issue gets a comment with a one-click suggestion, and one
  summary comment lists them all: tick the fixes you want and CodeMop commits them together
- **Learns what isn't a problem.** Resolve a conversation and it won't raise that again on the
  PR; reply `/codemop learn <why>` and it won't raise it again in the repository
- **Can block merges** while bugs or security issues are open, with a status you can require
- **Cheap enough for every push:** about 2–3¢ and a few seconds a review with the default
  model, which was chosen by an [eval](https://github.com/sgtwickool/codemop/blob/master/evals/review/README.md). Any provider, your own key, no
  CodeMop server

<!-- page: quickstart | Quick start | Review every pull request with CodeMop's GitHub Action, in two steps. -->
## Quick start: the GitHub Action

1. Add your model provider's API key as a repository secret: Settings → Secrets and
   variables → Actions → New repository secret, e.g. `ANTHROPIC_API_KEY`.
2. Add `.github/workflows/codemop.yml`:

```yaml
name: CodeMop
on:
  pull_request_target:
    types: [opened, synchronize, reopened, ready_for_review]
  issue_comment:
    types: [edited, created]  # fixes ticked in CodeMop's summary; `/codemop check`
  pull_request_review_comment:
    types: [created]  # someone replied `/codemop learn <why>` to a comment

permissions:
  contents: write  # to commit ticked fixes and learned notes
  pull-requests: write
  statuses: write  # for the merge check, if you turn it on

# Reviews: a new push replaces one still running. Commits (fixes, notes) wait their turn
concurrency:
  group: codemop-${{ github.event_name == 'pull_request_target' && 'review' || 'changes' }}-${{ github.event.pull_request.number || github.event.issue.number }}
  cancel-in-progress: ${{ github.event_name == 'pull_request_target' }}

jobs:
  codemop:
    # On comments, only edits of CodeMop's summary, `/codemop check`, and `/codemop learn` replies (not on forks' PRs)
    if: >-
      github.event_name == 'pull_request_target' ||
      (github.event_name == 'issue_comment' && github.event.issue.pull_request && (
        (github.event.action == 'edited' && contains(github.event.comment.body, 'codemop-summary')) ||
        (github.event.action == 'created' && startsWith(github.event.comment.body, '/codemop check')))) ||
      (github.event_name == 'pull_request_review_comment' && startsWith(github.event.comment.body, '/codemop learn') && github.event.pull_request.head.repo.full_name == github.repository)
    runs-on: ubuntu-latest
    steps:
      - uses: sgtwickool/codemop@v1
        with:
          api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

That's it: the next pull request gets a review. Drafts wait until they're ready for review.

<!-- page: responding | Responding to CodeMop | Fix, dismiss or teach: what to do with each issue CodeMop raises. -->
## Responding to CodeMop

CodeMop comments on each issue it finds, and keeps one summary comment in the PR's
conversation. For each issue:

| You want to | Do this | What happens |
|---|---|---|
| Fix it | Tick its box in the summary, and when you've ticked all you want, tick **Commit the ticked fixes** (or use "Commit suggestion" on its comment) | The ticked fixes are committed to the PR's branch as one commit, and marked as applied in the summary |
| Say it isn't a problem here | Resolve the comment's conversation | CodeMop won't raise it again on this pull request |
| Say it isn't a problem anywhere in the repository | Reply `/codemop learn <why it's fine>` to the comment | CodeMop adds a note to `.codemop-learned.yml` on the PR's branch, resolves the conversation, and replies to confirm. Once the PR is merged, it won't raise it again in the repository |

When you push more commits, CodeMop reviews just the new changes, and from then on raises only
bugs and security issues, so a one-line fix doesn't bring a new round of small points. The
summary keeps every issue from every review: open ones at the top, and under "Done" the ones
applied, addressed (their code changed; CodeMop resolves their conversation) or dismissed.
After a force-push or rebase, it reviews the whole pull request again.

- Ticking fixes and `/codemop learn` work for people with write access (CodeMop tells anyone
  else so). A fix is applied only where the code it replaces hasn't changed since the review;
  the summary says which were applied, and why any weren't
- `.codemop-learned.yml` is an ordinary file: read it, edit it, delete notes that are too
  broad. It's read from the default branch, so a pull request can't teach CodeMop to ignore
  its own bug
- GitHub doesn't run other workflows for commits made with the workflow's own token, so CI
  doesn't run on CodeMop's commits. To have it run, pass a personal access token (contents and
  pull requests: write) as `github-token`
- On pull requests from forks, CodeMop can't commit to the branch, and GitHub doesn't let
  workflows act on replies there: there are no checkboxes (the comments still have one-click
  suggestions) and `/codemop learn` doesn't work. Resolve the conversation instead, and add the
  note to `.codemop-learned.yml` on your default branch yourself

<!-- page: merge-check | Blocking merges | CodeMop's merge check: a status that fails while bugs or security issues are open. -->
## Blocking merges

CodeMop never approves or blocks a pull request on its own. To let it block merges, turn on
its merge check in `.codemop.yml` on your default branch:

```yaml
merge_check: true
merge_check_confidence: 0.8  # how sure it must be of an issue to block on it (default 0.8)
```

It then sets a commit status called **CodeMop** on each pull request's latest commit:

| Status | When |
|---|---|
| Pending | While it reviews, so nothing is merged mid-review |
| Failure | While any bug or security issue it's at least that sure of is open |
| Success | Once those are fixed, applied, addressed or dismissed; other kinds of issue never block |
| Error | When it couldn't review (an expired API key, say); the description says why |

Make it required in the branch's protection rules (Settings → Branches). A pull request too
large to review (`max-changed-lines`) passes, saying so, rather than being blocked forever.
The status is updated on every push and on CodeMop's own commits. GitHub runs no workflow when
a conversation is resolved, so after dismissing an issue that way, comment `/codemop check` on
the pull request to update it straight away.

<!-- page: configuration | Configuration | Every .codemop.yml setting and Action input. -->
## Configuring reviews

How a repository is reviewed goes in `.codemop.yml`, read from the default branch so a pull
request can't change it. Every setting is optional:

```yaml
ignore:              # paths not to review, added to the defaults (lock files, minified files...)
  - "docs/*"
  - "*.snap"
min_confidence: 0.6  # drop suggestions the model is less sure of (default 0.5)
max_comments: 5      # most inline comments in a review; the rest are listed in the summary (default 10)
chunk_tokens: 20000  # largest piece of diff sent in one request (default: the model's own)
merge_check: true    # see "Blocking merges"
```

It can't choose the provider, the model or where requests go, or raise what a review may cost:
whoever runs CodeMop decides that, in the workflow. Otherwise reviewing someone else's pull
request could send your API key to their server.

The Action's inputs:

| Input | Default | |
|---|---|---|
| `api-key` | (required) | The provider's API key, from a secret |
| `provider` | `anthropic` | `anthropic`, `mistral`, `openai`, `openrouter`, `ollama` or `openai-compatible` |
| `model` | the provider's | `claude-opus-5-5` for Anthropic, `codestral-latest` for Mistral; others need one named |
| `base-url` | | For `openai-compatible` or a self-hosted endpoint |
| `effort` | `high` | Claude's effort: `low` is cheaper and faster |
| `max-changed-lines` | `3000` | Don't review (or pay for) a pull request bigger than this |
| `max-comments` | the repository's, or 10 | Most inline comments in a review |
| `checklist` | `true` | The checkboxes in the summary |
| `context` | `true` | Send the code around each change too (see below) |
| `review-drafts` | `false` | Review draft pull requests too |
| `github-token` | the workflow's | A personal access token, so CI runs on CodeMop's commits |

**Context.** As well as the diff, CodeMop sends the whole of each changed function, where the
changed code is used in other files, and the definitions it uses (for Python today; other
languages get the lines around each change). A change can be right in itself and break the code
that calls it: in the eval, context took those bugs from 4/10 found to 10/10, for about 13% more
per review. The repository is read in one download, kept in memory, and never checked out or run.

<!-- page: models | Choosing a model | The providers and models CodeMop supports, and which the eval recommends. -->
## Choosing a model

The default is Claude Opus 5.5 at high effort, chosen by the
[review eval](https://github.com/sgtwickool/codemop/blob/master/evals/review/README.md): it found the most known issues, with almost no false
alarms. For less cost, `model: claude-sonnet-5-5` with `effort: low` was as good on simple
changes and missed a little more on complex ones. Claude Haiku 4.5 isn't recommended: half its
comments were wrong.

| Provider | Key (CLI environment variable) | Notes |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | The default |
| `mistral` | `MISTRAL_API_KEY` | Defaults to `codestral-latest` |
| `openai` | `OPENAI_API_KEY` | Name a model |
| `openrouter` | `OPENROUTER_API_KEY` | Name a model |
| `openai-compatible` | `--api-key-env` | Any OpenAI-compatible endpoint: set `base-url` and a model |
| `ollama` | none | A model on your own machine (CLI only; see below) |

<!-- page: privacy | Privacy | Exactly what CodeMop sends, and where. -->
## Privacy: what's sent where

CodeMop sends the diff, and with context the related code from the repository, to the model
provider you chose, with your key, and nothing else anywhere: there's no CodeMop server. The
review is posted on the pull request through GitHub's API with the workflow's token. Choose a
provider whose data terms suit your code (zero data retention, Bedrock, or a local model).

<!-- page: cli | The command line | Review a pull request or a local diff from your terminal. -->
## The command line

The same review runs anywhere Python 3.12+ does:

```bash
pipx install codemop                  # or: uv tool install codemop
export ANTHROPIC_API_KEY=sk-ant-...

codemop review owner/repo#123         # a pull request (GITHUB_TOKEN or `gh auth login` for private repos)
codemop review owner/repo#123 --post  # ...and post the review on it
git diff main | codemop review -      # your local changes
```

It prints each issue with its file and line, the reason, and a fix where it has one, then the
tokens used and an estimated cost; `--json` prints it for scripts. `codemop review --help` lists
every option, including `--provider`, `--model` and `--no-context`. A commit already reviewed
with `--post` isn't reviewed (or paid for) again.

**With a local model (Ollama):** no API key, no cost per review, and the code never leaves your
computer. It's slower, and small models review less well.

```bash
ollama pull qwen2.5-coder:7b
codemop review owner/repo#123 --provider ollama --model qwen2.5-coder:7b
```

Ollama gives models a 4,096-token context window by default, which is too small: set
`OLLAMA_CONTEXT_LENGTH=16384` for the Ollama server and restart it. CodeMop checks the token
count Ollama reports back, and stops with an error rather than review a fragment.

## More

- [Self-hosting the webhook server](https://github.com/sgtwickool/codemop/blob/master/docs/self-hosting.md): the older way to run CodeMop, as a
  server with a database, for setups the Action doesn't suit
- [Security](https://github.com/sgtwickool/codemop/blob/master/SECURITY.md): reporting a vulnerability, and why fork PRs are safe to review
- [Contributing](https://github.com/sgtwickool/codemop/blob/master/CONTRIBUTING.md), the [changelog](https://github.com/sgtwickool/codemop/blob/master/CHANGELOG.md), the [roadmap](https://github.com/sgtwickool/codemop/blob/master/ROADMAP.md),
  and the [product design](https://github.com/sgtwickool/codemop/blob/master/docs/product.md)
- [The review eval](https://github.com/sgtwickool/codemop/blob/master/evals/review/README.md): how the default model was chosen, and how changes
  to the review are measured

MIT licensed.
