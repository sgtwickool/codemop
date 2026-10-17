# AI code review on pull requests from forks, safely

Most open-source pull requests come from forks, written by people you don't know. They're the
ones that most need a first review, and the ones most AI reviewers running in GitHub Actions
skip. Here's why, and how CodeMop reviews them anyway.

## The problem

An AI reviewer needs your model API key. In GitHub Actions, a workflow started by a fork's pull
request (`pull_request`) runs without your repository's secrets, so the reviewer has no key.
Claude's own GitHub Action, for example, says that "the review runs only on pull requests from
branches in the same repository".

There is a way to get the secrets: `pull_request_target`, which runs the workflow as your
repository's default branch, with its secrets and a token that can write. But if that workflow
checks out the pull request's code and runs any of it (installing dependencies, running a build,
or giving an agent tools to explore it), a stranger's code runs with your key. GitHub calls this
a ["pwn request"](https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/).
An agent that can run commands is exactly the kind of tool that can be talked into running one.

So most tools pick one of:

- **Don't review forks automatically**: a maintainer asks for each review
- **A hosted service**: the reviewer runs on its maker's servers with its own credentials, which
  means sending your code to them

## How CodeMop does it

CodeMop runs on `pull_request_target`, so it has your key on every fork pull request. It's safe
because of what it never does:

- **It never checks out or runs the pull request's code.** It reads the diff, and the repository
  around it, through GitHub's API, and keeps them in memory. Nothing from the pull request is
  written to disk, installed or run
- **The model has no tools.** It gets text and returns text. It can't run commands, read files
  or make requests, so there's nothing for a malicious pull request to talk it into
- **The pull request can't change how it's reviewed.** Settings are read from your default
  branch, never the pull request's, and they can't choose the model, the endpoint or what a
  review may cost, so no pull request can send your key somewhere else
- **Nothing is committed unless someone with write access asks.** A suggested fix is only
  committed when a maintainer ticks it

The worst a hostile pull request can do is try to steer what the review says (prompt
injection): hide a problem, or suggest a bad fix. That's why fixes are committed only when a
maintainer has read them and ticked them. [Security](../../SECURITY.md) has the details.

## Set it up

The [quick start](../../README.md#quick-start-the-github-action) is the whole setup: a secret
with your model provider's key, and one workflow file. Every pull request, including forks',
gets a review on the next push.
