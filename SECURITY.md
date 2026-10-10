# Security

## Reporting a vulnerability

Please report it privately, not in a public issue: on GitHub, go to the repository's
**Security** tab and choose **Report a vulnerability**. Reports are acknowledged, fixed in a
new release, and credited in the release notes if you'd like.

Fixes go into the latest release, and the Action's `v1` tag moves to it. Older releases aren't
patched.

## How CodeMop keeps your key and repository safe

CodeMop's Action runs on `pull_request_target`, so it has your model API key and a token that
can write to the repository even on a pull request from a fork, written by anyone. That's what
lets it review every fork PR automatically, and it's safe only because of the rules below.
They're the first of the [product design's rules](docs/product.md#the-rules-it-doesnt-break),
and every change has to keep them.

- **It never checks out or runs the pull request's code.** It reads the diff, and for context
  the repository at the PR's commit, through GitHub's API, and holds them in memory. Nothing
  from the PR is written to disk, installed or run. Don't add `actions/checkout` of the PR to
  CodeMop's job
- **The model has no tools.** It's sent text and returns text; it can't read files, run commands
  or make requests
- **The pull request can't change how it's reviewed.** `.codemop.yml` and `.codemop-learned.yml`
  are read from the default branch, not the PR's. And `.codemop.yml` can't choose the provider,
  model or endpoint, or raise what a review may cost, so no repository can send your key to
  its own server
- **Nothing is committed unless someone with write access asks.** Fixes are committed only when
  a person with write access ticks them in the summary, and `/codemop learn` only works for
  people with write access. Ticks and commands from anyone else are ignored, with a reply saying
  why. CodeMop never commits to a fork's branch
- **It only trusts its own comments.** It acts on a summary or comment only if it was posted by a
  bot (the workflow's token) or someone with write access, so a copy of CodeMop's summary posted
  by someone else can't commit anything
- **Your key stays in the job.** The Action passes it to the `codemop` command in an environment
  variable and doesn't print it. The GitHub token is sent only to GitHub's API (not to the
  download server GitHub redirects the repository snapshot to)

The workflow needs `pull-requests: write` to comment, `contents: write` to commit ticked fixes
and learned notes, and `statuses: write` for the merge check. Leave out `contents: write` and
`statuses: write` if you don't use those.

## Accepted risks

- **A pull request's text can try to steer the review** (prompt injection): code or comments
  written to make the model miss a problem, or post a misleading comment or a harmful
  suggested fix. The model can't act on anything, so the worst outcome is a bad comment. A
  suggested fix is only committed when someone with write access ticks it, having seen it in
  full. So read fixes on strangers' PRs before ticking them, as you would read their code
- **The merge check is a safety net, not a guarantee.** It fails while CodeMop has found bugs or
  security issues, and a review can miss things, more so if the author is trying to make it.
  Keep human review for what matters
- **CI doesn't run on CodeMop's own commits** with the workflow's token (GitHub doesn't start
  workflows for them). Pass a personal access token as `github-token` if it must
- **The self-hosted server** binds to `0.0.0.0` in its container (put it behind your own network
  rules), and Bandit's `assert` (B101) and SQL-string (B608) checks are skipped for it: asserts
  aren't used for security, and its SQL is built by SQLAlchemy

## What CI checks

Every pull request and a weekly run: `pip-audit` fails the build on a dependency with a known
vulnerability; Bandit checks the package and the server; Trivy scans the server's container
image (reported, not failing, since base images often have issues without a fix yet). Dependabot
opens monthly update pull requests for Python, GitHub Actions and Docker dependencies.
