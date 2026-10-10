# Changelog

What changed in each release of the `codemop` package and the GitHub Action. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[semantic versioning](https://semver.org/).

## Unreleased

To be 1.0.0, the first release of the GitHub Action.

### Added

- **The GitHub Action** (`uses: sgtwickool/codemop@v1`): reviews every pull request, including
  ones from forks, on `pull_request_target`, without checking out or running their code
- `codemop review --post`: posts the review on the pull request, as a comment on each issue
  with a one-click suggestion where there's a fix, and one summary comment that later reviews
  update in place. A commit already reviewed isn't reviewed again
- **Fixes you tick:** a checkbox in the summary for each fix, and **Commit the ticked fixes**,
  which commits everything ticked as one commit (`codemop apply`). One problem in several places
  is one checklist item
- **Learning:** resolving a conversation dismisses its issue for the pull request; replying
  `/codemop learn <why>` adds a note to `.codemop-learned.yml`, so it isn't raised again in the
  repository (`codemop learn`)
- **Re-reviews:** a new push is reviewed from the last commit reviewed, raising only bugs and
  security issues; conversations whose code has been fixed are resolved
- **The merge check:** with `merge_check: true` in `.codemop.yml`, a "CodeMop" commit status that
  fails while bugs or security issues are open, for branch protection to require;
  `/codemop check` updates it (`codemop check`)
- **Repository context, on by default:** the whole of each changed function, where the changed
  code is used in other files, and the definitions it uses (Python). `--no-context`, or the
  Action's `context: false`, turns it off
- `--max-changed-lines N`: doesn't review a diff larger than this (a cost limit)
- Each suggested fix is checked to fit the lines it replaces, and left out if it doesn't

### Fixed

- Reading pull requests with more than 100 comments
- Ticks made on GitHub's web page (which saves the comment with Windows line endings)
- GitHub requests that fail briefly are tried again

## 0.1.0 (2026-10-09)

The first release on PyPI: `codemop review` reviews a pull request (`owner/repo#123` or a URL)
or a diff on stdin and prints the issues it finds, with a fix where it has one, and the cost.

- Providers: Anthropic (the default, Claude Opus 5.5 at high effort, chosen by the review eval),
  Mistral, OpenAI, OpenRouter, Ollama and any OpenAI-compatible endpoint
- `.codemop.yml` on the default branch says how a repository is reviewed (ignored paths, minimum
  confidence, chunk size), and can't choose the provider or model
- `--json` for scripts
