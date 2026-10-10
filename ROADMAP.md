# CodeMop Roadmap

CodeMop reviews pull requests with AI and suggests fixes. The goal is a tool that is
useful day to day and that anyone can adopt in a couple of minutes, with no server to run.

This roadmap replaces the original scope documents, now in `docs/archive/` (see [Decisions](#decisions)).
[`docs/product.md`](docs/product.md) is the product design: who it's for, the rules it doesn't
break, and how ideas are judged.
Phases are worked through in order. Each phase has a "done when" line, so it's clear when
to move on.

## Why CodeMop

Claude already reviews PRs (its GitHub Action, on an API key or a Pro/Max subscription, and a
managed Code Review for Team and Enterprise plans at about $15–25 and 20 minutes a review), so
"use your subscription" isn't a reason to choose CodeMop. These are:

- **Reviews fork PRs automatically and safely:** CodeMop reads only the diff, through the API,
  never checks out or runs the PR's code, gives the model no tools, and takes its settings from
  the default branch. So it can hold a key on fork PRs, where agents that run tools on the code
  can't (Claude reviews forks only when a maintainer asks). Open-source maintainers get most of
  their PRs from forks
- **Fixes, not just findings:** one-click suggestion blocks, and a summary comment, edited in
  place, with a checklist: tick the fixes you want and CodeMop commits them as one grouped commit
- **Learns from you, visibly:** reply "intentional" or 👎 a comment and it's resolved and
  remembered in a file in the repo that you can read and edit; it isn't raised again. Re-reviews
  look at new commits only, report important findings only, and resolve threads once the code is
  fixed (Claude's Action is swayed by old comments, and replies to Code Review do nothing)
- **Cheap and fast enough for every push:** about 2–3¢ and 5 seconds a review (the
  [eval](evals/review/README.md)), with deeper, costlier review only where a change needs it
  (tiered review, Phase 8)
- **For teams Anthropic's managed review doesn't serve:** any provider, your own key (including
  zero data retention or Bedrock), only `pull-requests: write`, and a check that can fail on
  major findings (Claude's is always neutral). Later GitLab and Gitea/Forgejo, which have
  nothing like it
- **Reviews a feature across repositories** (Phase 9): the frontend and backend PRs that ship
  together, reviewed as one change

Where Claude is ahead: it reads the whole repository, verifies findings with several agents,
and needs no setup. Tiered review closes the first gap by using Claude Code's own review as the
deep tier.

## How we work

- **Every change is a pull request** (since 2026-10-09; before that, commits went straight to
  `master`). CodeMop's own workflow reviews each one, so working on CodeMop is also using it.
  Merge when CI is green and the review's real findings are dealt with. Dependabot's monthly
  update PRs are reviewed and merged as they come.
- **`/simplify` at the end of every phase**, over that phase's diff (`git diff phase-N-1..HEAD`).
  Also run it on any single change of more than about 300 lines. Then tag the end of the phase
  (`phase-N`) so the next pass has a clean starting point.
- **`/simplify` only sees changed code**, so each end-of-phase tidy also sweeps for dead code in
  files nobody touched (functions that are never called, files that are never imported).
- **Keep the structure honest:** follow the layout below, and update it here before adding a new
  top-level folder. A module that grows past about 300 lines, or that changes for two unrelated
  reasons, gets split into a package. Code that talks to an outside service (GitHub, a model
  provider) lives together. Unused code is deleted, not kept "for later"; git remembers it.

## Repository structure

The layout:

```
codemop/
├── action.yml            # the GitHub Action (it must be at the root for `uses: sgtwickool/codemop@v1`)
├── pyproject.toml        # the `codemop` package (core + CLI), published to PyPI
├── src/codemop/
│   ├── review/           # diff -> per-file chunks -> prompt -> validated suggestions; fixes, context, learned notes
│   ├── providers/        # one module per model provider, behind one interface
│   ├── github/           # GitHub: the API (api.py gathers the calls), inline comments, the summary, the merge check
│   └── cli/              # the codemop command: a module per subcommand (review, apply, learn, check)
├── tests/                # tests for the package, mirroring src/codemop/ (tests/cli: the commands, with a fake GitHub)
├── evals/                # the review eval: does a model or prompt change make reviews better?
├── server/               # the optional self-hosted webhook server, using the package
├── site/                 # the website, codemop.com: Astro + Starlight; its docs pages are written from the markdown here
├── docs/                 # design notes; docs/archive/ for superseded plans
└── scripts/              # developer scripts
```

---

## Phase 0: Get to green

A fresh clone installs, runs, and passes CI.

- [x] Pin dependencies; split runtime (`requirements.txt`) from dev/test tooling (`requirements-dev.txt`)
- [x] Remove unused dependencies (`python-jose`, `passlib`, `cryptography`, `python-multipart`, `pytest-xdist`)
- [x] Remove the unused SQLAlchemy asyncio import (it pulled in `greenlet`)
- [x] Load `.env` from the repo root instead of a hardcoded home-directory path
- [x] Support SQLite for local runs and tests (no pool arguments on SQLite)
- [x] Use a single shared rate limiter; return errors in one consistent `{"detail": ...}` shape
- [x] Webhook: reject malformed or non-object JSON (422) and non-JSON content types (415)
- [x] Suggestions endpoint: 404 for unknown PRs, the same response shape with or without suggestions, no exception text in errors
- [x] Tests: deterministic settings, no network access, no dependence on the developer's `.env`, isolated database per test, and fixes for the tests that were wrong
- [x] Fix `scripts/setup_dev.sh`, the Docker healthcheck, and the CSP that blanks the Swagger docs
- [x] Fix factual errors in the README (webhook path, test commands, badges)
- [x] Replace Safety (needs an account, and its failures were being swallowed) with pip-audit
- [x] CI installs dev requirements and passes on Python 3.12–3.14
- [x] Docker workflow: set up Buildx (the runner's default driver can't export the build cache)

**Done when:** `pip install -r backend/requirements-dev.txt && pytest` passes on a clean
machine, and CI is green.

## Phase 1: Make the server correct for real use

The webhook server keeps working, and later becomes the optional self-hosted mode
(see "Later"). Analysis-quality and model-provider work moves to the shared core in Phase 2;
the server switches to that core when it lands.

- [x] Add Alembic migrations; stop relying on `create_all` (existing databases are stamped and upgraded)
- [x] Identify a PR by `(repo_full_name, number)`, not the PR number alone (PRs in different repos overwrote each other)
- [x] Run the test suite against PostgreSQL in CI (SQLite hid two bugs: long titles and large PR numbers caused 500s)
- [x] Move the compose files to Postgres 17 (13 is end of life), then 18
- [x] Bring the GitHub Actions (1-3 majors behind; Trivy was unpinned), the Docker base image (Python 3.14) and Postgres (18) up to date; the Python packages were already current
- [x] Keep dependencies current automatically: Dependabot, monthly, one grouped PR per ecosystem (pip, Actions, Docker, compose)
- [x] Upsert PRs in a single statement, so concurrent deliveries for the same PR can't collide
- [x] De-duplicate deliveries by `X-GitHub-Delivery` (GitHub redelivers on timeouts and manual retries)
- [x] Prune old delivery records (kept for 7 days; pruned on each webhook, using an index)
- [x] Return from the webhook within 1s; run analysis in the background (measured: 0.08s with an 8s diff fetch behind it)
- [x] Analyse only on `opened`, `synchronize`, `reopened` and `ready_for_review` (not drafts, not already-analysed commits); replace old suggestions per head SHA, discarding results for superseded commits
- [x] Store PR state (open/closed/merged), not the last webhook action
- [x] Refuse to start without `GITHUB_WEBHOOK_SECRET` and `API_KEY` (outside dev; `APP_ENV` now defaults to `production`); compare keys in constant time
- [x] Validate signatures on every event, not just `pull_request` (and answer GitHub's `ping`)
- [x] Fetch diffs through the GitHub REST API with an optional `GITHUB_TOKEN`, so private repos work (checked against this repo, which is private); errors say what to fix
- [x] Look up suggestions by repo + PR number (`GET /api/v1/repos/{owner}/{repo}/pulls/{number}/suggestions`)
- [x] Rethink the webhook rate limit: removed, since it could only drop GitHub's own deliveries (they share a few IPs, or a proxy's, and GitHub doesn't retry a 429); signatures and once-per-commit analysis are the protection
- [x] Fix Prometheus metrics (the middleware bound `None` at import, so nothing was recorded) and label them by route template, not raw path; the metrics server is off unless `ENABLE_METRICS=true`
- [x] Replace `print` with logging (and stop the JSON logs escaping non-ASCII); tighten CORS: off unless `CORS_ORIGINS` lists origins, never with credentials
- [x] End-of-phase tidy: `/simplify` over the Phase 1 diff, then remove dead code it can't see (unused helpers, the committing `BaseRepository` methods, the `src/main.py` shim, the side-effecting `app/__init__.py` import)
- [x] Check the "done when" end to end: a real webhook for this repo's PR #2 (private) was stored and its diff fetched; the AI call failed only because the old Mistral key has expired. The real-model check moves to Phase 2, with Claude. Tagged `phase-1`

**Done when:** a real PR on a real (including private) repo gets stored suggestions,
with no GitHub delivery failures. *(Closed on 2026-10-07 with everything up to the AI call
verified; the stored-suggestions check is done in Phase 2 with Claude.)*

## Phase 2: Core package and CLI

Extract the review logic into a package that has nothing to do with FastAPI or the database.

- [x] `codemop` core: diff → per-file chunks → prompt → model → validated suggestions, with one report of what was reviewed, skipped, set aside or failed
- [x] Handle large diffs by chunking per file (and per hunk for big files) instead of cutting off at 10k characters; report anything skipped
- [x] Map suggestions to diff positions (GitHub only accepts comments on lines in the diff); set aside ones that aren't
- [x] Config file `.codemop.yml`: ignored paths, minimum confidence, chunk size; read from the repo's default branch by both the CLI and the server. It deliberately can't choose the provider, model or endpoint (see the decisions table). Max comments comes with posting, in Phase 3
- [x] CLI: `codemop review owner/repo#123` (or a PR URL, or `-` for a diff on stdin) prints the review; `--json` for machines. Posting comes with `--post` in Phase 3. Uses `GITHUB_TOKEN`, or the `gh` login, for private repos
- [x] Golden tests from recorded diffs and model responses: `tests/golden/` replays real recorded answers (Claude Opus 5.5 from the eval, and a local model over three chunks) through the whole review and checks what's sent to the model and both reports; `record.py` records a new case
- [x] The server reviews with the package; its own Mistral-only AI code, response parser and diff fetcher are gone. Configured with `AI_PROVIDER`, `AI_MODEL`, `AI_BASE_URL` and `AI_API_KEY`
- [x] Move to the target [repository structure](#repository-structure): the package at the root, `backend/` became `server/` and uses it
- [x] In the server, stop running synchronous database work inside `async` handlers and the background job (make DB-only handlers plain `def`, or move to async SQLAlchemy); it blocks the event loop under load. (The suggestions endpoints are plain `def`; the webhook and the background review do their database work in the thread pool; tests check none of it runs on the event loop)
- [x] Move the older integration tests' inline payloads and headers onto `tests/helpers.py` / the `post_webhook` fixture
- [x] Publish to PyPI: [codemop 0.1.0](https://pypi.org/project/codemop/) (2026-10-09), from `v*` tags by `release.yml` with trusted publishing; each release waits for approval in the `pypi` environment

### Model agnostic

Users bring their own provider and key, and review quality varies a lot between models,
so the core must not care which model it's talking to, and the choice of default must be measured.

- [x] A single `ReviewModel` interface the rest of the code depends on; provider SDKs are imported only inside their adapters
- [x] Adapters: Anthropic (official `anthropic` SDK, not an OpenAI-compatible shim, so structured output and refusal handling work properly), and one OpenAI-compatible adapter that covers Mistral (its API is OpenAI-compatible, structured output included), OpenAI, OpenRouter and local models through Ollama or vLLM
- [x] Each adapter uses its provider's native structured output (for Anthropic, `output_config.format` / `messages.parse()`). Every result is then validated against the same Pydantic schema, with one repair retry for providers that don't enforce a schema. Drop the plain-text scraping fallback
- [x] Avoid provider-specific tricks that are going away: current Claude models reject both forced `tool_choice` and assistant-message prefill (structured output instead)
- [x] Detect input a server silently dropped (Ollama does when a request doesn't fit its context window): CodeMop compares the reported token count with what it sent and stops with a fix, rather than reviewing a fragment
- [x] Treat non-answers as such: refusals, truncated output (`max_tokens`), rate limits and a rejected API key produce "no review, because …" (saying what to fix, like the GitHub errors do), and are never parsed as suggestions
- [x] Token budgets: chunks are planned with a deliberately high estimate (3 characters per token), so they're never too big for `chunk_tokens`; real usage comes back on every response. (Counting exactly with each provider's endpoint would cost an API call per file and hunk while planning)
- [x] Config: `provider`, `model`, `api_key_env`, optional `base_url`, from flags or `CODEMOP_PROVIDER` / `CODEMOP_MODEL` / `CODEMOP_BASE_URL` (the server: `AI_*`); no model IDs hardcoded outside the defaults
- [x] Record tokens and estimated cost per run (list prices, dated; no estimate for models without a known price). (Prompt caching doesn't help yet: the shared instructions are a few hundred tokens, below Claude's minimum cacheable prefix of 1,024+)
- [x] **Model comparison eval:** a fixed set of real PR diffs with known issues, scored the same way for every provider and model (real issues found, false positives, valid line positions, cost per useful comment). It picks the default, catches regressions when prompts or models change, and later measures complexity-based routing (Phase 6). (2026-10-08: [`evals/review/`](evals/review/README.md), 25 cases (real bugs from this repo's history, seeded bugs, clean changes), five Claude configurations, graded by location and a Claude Opus 4.8 judge; about $9 for the full run)
- [x] End-to-end check carried over from Phase 1: a real PR through the server with Claude ends with stored suggestions. (2026-10-07: a real webhook for PR #2 went through the server, the package and claude-opus-5-5 in 12s, and 3 suggestions were stored; the CLI reviewed the same PR in 11s for about $0.02. Done with a local qwen2.5-coder:7b too)
- [x] One `min_confidence` for the CLI and the server: 0.5 by default, or the repo's `.codemop.yml`
- [x] Choose the default model from the eval. Start by comparing Claude Opus 5.5 (`claude-opus-5-5`) against cheaper options, Codestral (the current default) and a local model. (2026-10-08: Claude Opus 5.5 at high effort stays the default: 47/50 cases passed, best on complex changes, about $0.02 a review. Sonnet 5.5 matched it on simple changes for 40% of the cost; Haiku 4.5 got half its comments wrong. Codestral wasn't compared (no key); the local model is for demonstration only)

**Done when:** `pipx run codemop review sgtwickool/codemop#N` prints useful suggestions
with at least two providers, and the eval results are in the repo. *(Done 2026-10-09:
0.1.0 from PyPI, run with `uvx`, reviewed PR #2 with Claude Opus 5.5 (22s, 2¢; nothing
above the confidence threshold, correctly: the file's "intentional issues" are style) and
with a local qwen2.5-coder:7b (9 minutes on a CPU; one false alarm, and fixes that replace
the whole function, the case Phase 3's suggestion check is for). On commit 467452c it found
both known bugs for 4¢. Tagged `phase-2`)*

## Phase 3: GitHub Action and dogfooding

How people will use CodeMop: a GitHub Action with their own key for any provider, built on the
core package. This phase includes what makes it worth choosing over Claude's own reviews (see
[Why CodeMop](#why-codemop)), not just a wrapper around the CLI.

### GitHub Action

- [x] `action.yml` wrapping the CLI (`uses: sgtwickool/codemop@v1`), with `provider`, `model` and `api-key` inputs (a composite action: installs CodeMop from its own source into a separate environment, inputs reach the script only as environment variables, drafts skipped)
- [x] Post a single PR review with inline ```` ```suggestion ```` blocks (one-click apply) plus a summary (`codemop review owner/repo#N --post`; a commit already reviewed isn't reviewed again)
- [x] Check each `suggested_code` really replaces lines `line..end_line` before posting it as a suggestion block: small models often include the line above or below, which GitHub would then duplicate (seen with qwen2.5-coder:7b). (Repeated lines at the edges are trimmed; a fix that still repeats nearby code is left out, and the comment kept)
- [x] Cost guardrails: maximum diff size and maximum number of comments (`--max-changed-lines`, set by whoever runs it, 3000 in the Action; `max_comments` in `.codemop.yml`, default 10)
- [ ] Review fork PRs automatically: a `pull_request_target` workflow that reads the diff through the API and never checks out the PR's code, so the key is safe (see [Why CodeMop](#why-codemop)); document why it's safe, and the permissions (`pull-requests: write`)

### Fixes you can apply

- [x] One summary comment, edited in place on every run, listing the findings as a checklist
- [x] Grouped fixes: related findings (the same mistake in several places, or one fix that spans files) become one item with one fix (the model labels them with `group`; one checkbox commits them all. The eval held on what decides a pass, 2026-10-09)
- [x] Tick items and CodeMop commits those fixes to the PR branch as one commit (an `issue_comment` edited trigger; only from people with write access). Fork branches can't be pushed to, so there it falls back to suggestion blocks. (`codemop apply`; committed through the API, so nothing is checked out. Commits made with the workflow's own token don't start CI (their checks show as failed to start): documented, with a personal access token as the fix. Tested end to end on 2026-10-09 with a throwaway PR, #7: ticked with browser-style line endings, committed in one commit and marked applied)
- [x] A **Commit the ticked fixes** box: ticking a fix only selects it, so any number go in one commit (2026-10-09: each tick is its own workflow run, and GitHub keeps only one waiting, so quick ticks used to land as two commits)
- [x] Check every fix still applies to the current code before committing it, and say so when one doesn't (where the code has moved, the original lines are found again if they're there exactly once)

### Learns from you

- [x] Reply "intentional" (or 👎) to a comment: CodeMop resolves it and doesn't raise it again on this PR. (Done as resolving the conversation instead: it's GitHub's own gesture, needs no syntax, works on forks' PRs, and GitHub sends no event for reactions. The next review reads which threads are resolved)
- [x] Remember it for the repository too: add it to a memory file in the PR branch, so it's visible in the diff, read from the default branch like the rest of the config (so a PR can't quietly teach it to ignore its own bug), and editable by hand. Only from people with write access. (Reply `/codemop learn <why>`: a note in `.codemop-learned.yml`, the thread resolved, and a reply saying what happened. The summary and every comment say how to respond)
- [x] Re-reviews look at the new commits only, report important findings only after the first review, and resolve threads whose code has been fixed. (The summary keeps every finding with a status: open, applied, addressed or dismissed. A force-push or rebase gets a full review; files a merge of the base brought in are left out)

- [x] At the end of the phase, split `cli.py` (about 600 lines) into a package with a module per command, and `github/client.py` (about 470) by area; the CLI tests patch functions on `cli`, so they move with it. (`codemop/cli/` has a module per command; `github/` has client (requests), pulls, conversation and commits, gathered in `github/api.py`, which is also what tests fake; the CLI tests are in `tests/cli/`)

### Merge check

- [x] A check run that can fail on major findings above a confidence threshold (off by default; set in `.codemop.yml`), so branch protection can block a merge. (A "CodeMop" commit status, not the workflow's own result: pull_request_target runs report against the base branch's commit. Pending during reviews, an error when a review fails, and updated on CodeMop's own commits and by commenting `/codemop check`, since GitHub runs no workflow when a conversation is resolved)

### Repository context

- [x] Send the cheap review more than the diff: the whole of each changed function, and the definitions and callers of what it uses, found without a model (e.g. tree-sitter or ripgrep), within a token budget. Most of the eval's misses on complex changes needed this. (2026-10-09: whole functions, same-file definitions and Python imports, with the standard library's ast; `--context`, off by default: see below)
- [x] Measure it with the eval before and after. (No measurable gain: 44/50 with it, 47/50 without, within the noise, for about 12% more cost. Most real cases created whole files, so the diff already shows what it adds, and what they lack is in callers in other files. Details in `evals/review/README.md`)
- [x] Callers: where the changed functions are used, from other files (the context the eval's misses needed), and eval cases whose bugs depend on other files; turn context on by default once it measurably helps. (2026-10-09: where what the change defines is used, in files that import it; on GitHub, the repository comes in one download, kept in memory. Seven cross-file eval cases: those bugs went from 4/10 found to 10/10, for about 13% more per review, so context is on by default. Details in `evals/review/README.md`)

### Dogfooding

- [ ] Run it on CodeMop's own PRs for at least two weeks (the workflow is in place, 2026-10-09: `.github/workflows/codemop.yml`, its first review on PR #2; the two weeks start once our work goes through PRs)
- [ ] Tag `v1`; list on the GitHub Marketplace
- [x] Tidy: `/simplify` over the Phase 3 diff so far. One rule for "the same issue" (`same_issue`), the checklist in its own module, comments that carry their finding's id, the commands on shared helpers (`cli/common.py`, `cli/post.py`, `cli/report.py`), files read once even when chunks ask at the same time, and committing reads only the changed directories' trees

**Done when:** someone else installs it from the README alone and it reviews their PR.

## Phase 4: Docs cleanup

- [x] Rewrite the README around the Action quickstart; move server setup to a self-hosting doc (`docs/self-hosting.md`)
- [x] `CONTRIBUTING.md` (dev setup, tests, branch naming)
- [x] `SECURITY.md` (how to report issues, plus the accepted risks from `SECURITY_DECISIONS.md`). Most of that file no longer applied (the ecdsa and Safety exceptions are gone); `SECURITY.md` explains the Action's threat model and the risks still accepted
- [x] `CHANGELOG.md`
- [x] Archive the original scope and epics to `docs/archive/`; delete or archive the local process docs (`PHASE_1_IMPLEMENTATION.md`, `BRANCH_STRATEGY_UPDATE.md`, `CI_CD_ROLLOUT_PLAN.md`, `STEERING.md`, `TESTING_GUIDE.md`, `server/docs/`). (2026-10-10: archived and deleted; private vulnerability reporting turned on for `SECURITY.md`)

## Phase 5: Website (marketing and docs)

- [x] Astro + Starlight site in `site/`, so the docs are versioned with the code. (2026-10-10: the docs pages are written at build time from the README's sections, `docs/self-hosting.md`, `SECURITY.md`, `CHANGELOG.md` and `CONTRIBUTING.md`, so there's one copy; the Site workflow builds it on every PR that touches them)
- [x] Match the look of kempgt.com (fonts, palette) and reuse the animated `mop()` print. (It's gregkemp.dev now: its fonts, paper and inks, and its art library, with two new prints for the review loop; a real review from PR #20 you can tick)
- [x] Pages: landing (pitch, demo GIF of a real review, two-minute setup), Quickstart (the Action), Configuration, Supported models, Privacy (exactly what code is sent where), Self-hosting, Changelog. (The demo is a live, tickable copy of a real review rather than a GIF; also Responding, Blocking merges, the CLI, Security and Contributing)
- [x] Deploy at `codemop.com` (GitHub Pages, from the Site workflow); link it from the CodeMop card on gregkemp.dev. (2026-10-10: live at [codemop.com](https://codemop.com) with HTTPS; the card links to it from kempgt.com#3, the first PR CodeMop reviewed outside this repository)

- [x] A mascot for the hero (2026-10-10): a fretful little mop, designed on a canvas over nine takes. He plays his routine once as the page loads (mops up the dirt, taps the crooked picture straight with his handle, scurries back for a speck he missed), then peeks in now and then looking for more; still for reduced motion

**Done when:** the gregkemp.dev card links to a live site with a working quickstart.

## Phase 6: v1.1, everyone's reviews

After v1. The order of Phases 6–9, and what each is for, come from the
[product design](docs/product.md).

- [x] Repository context for TypeScript and JavaScript, then Go: the function around a change,
  what the change defines and where it's used, with `tree-sitter` and its prebuilt grammars
  behind the same steps as Python. (2026-10-10: TypeScript and JavaScript, with JSX, path aliases
  like Next.js's `@/…`, and ESM imports; `codemop.review.code` has a reader per language. Go later)
- [x] Cross-file eval cases in TypeScript, like the Python ones (3 bugs and a clean change: with
  context 8/8, without 4/8, and the two TypeScript bugs only found with it)
- [ ] `codemop stats owner/repo`: from the summaries on recent PRs, the share of findings acted on
  (applied or addressed) against dismissed, by severity, and what reviews cost. Read from the PRs;
  nothing is sent anywhere

**Done when:** a TypeScript PR gets the same kinds of context as a Python one, the TypeScript
cases pass with it, and `codemop stats` reports on CodeMop's own PRs.

## Phase 7: v1.2, explain

Teaching mode, for people shipping code they didn't write and don't fully follow (mostly
their agents').

- [ ] Reply `/codemop explain` to one of CodeMop's comments: it replies with the concept behind
  the mistake, why it's easy to make (and why agents often do), and links to official
  documentation
- [ ] Comment `/codemop explain` on the PR: the summary gains a short walkthrough of what the
  change does and how its parts fit together
- [ ] `explain: true` in `.codemop.yml`: every comment gains a collapsed "Learn more" section
- [ ] Links only to official documentation sites, each checked to load before it's posted
- [ ] Measured: the judge grades explanations for accuracy, and the eval checks every link

**Done when:** explanations pass the eval's accuracy check with no broken links, and both
commands work on a real PR.

## Phase 8: v1.3, tiered review

A cheap triage step picks, per PR:
1. **Skip:** only what's certainly trivial (docs only, lock files, pure renames, whitespace),
   decided by rules, not a model
2. **CodeMop's review** (2–3¢): the diff with repository context
3. **Claude Code's `/code-review` at low effort**, which reads the whole repository
4. **`/code-review` at high effort, or ultrareview**, for risky or wide-reaching changes
   (auth, payments, migrations, concurrency, public APIs, large logic changes)

- [ ] The triage: a capable model at low effort (e.g. Claude Sonnet) given the diff, the files'
  paths and the size of the change. It never downgrades code the rules mark as risky, and the
  summary says which tier reviewed the PR and why. Tiers configurable in `.codemop.yml`
- [ ] Tiers 3 and 4 as a conditional step using Anthropic's own `claude-code-action`, so they can
  bill the user's Claude subscription the supported way. They check out the PR's code, so on
  fork PRs only tiers 1 and 2 run automatically, and a maintainer opts in to more (rule 1)
- [ ] The deep tiers' findings in CodeMop's summary and checklist, so there's one place to
  respond (rule 5); their own comments first, as a step to it
- [ ] Measured: Claude Code's `/code-review` at low and high effort as eval configurations, which
  also says how close CodeMop's own review gets to it

**Done when:** the eval shows the tiers together find more than CodeMop's review alone on the
complex cases, for less than reviewing everything at the deep tier.

## Phase 9: v1.4, cross-repository review

PRs in different repositories that ship together (a frontend and the backend it calls),
reviewed as one change, for the bugs that come from mismatches: request and response shapes,
field names, types, error codes, feature flags, the order they have to deploy in.

- [ ] Linking: the same branch name across repositories (the usual habit when working in several
  worktrees), or a line in the PR description such as `Ships with: org/backend#42`; the
  repositories that can be linked are listed once, in `.codemop.yml` on the default branch
- [ ] Each linked PR gets the same combined review, with each comment on the PR it belongs to; it
  runs once, when the last linked PR is opened or updated
- [ ] Reading the other repositories: a GitHub App or a fine-grained token, since an Action's own
  `GITHUB_TOKEN` only covers its own repository
- [ ] Measured: eval cases made of linked pairs of diffs

**Done when:** a linked frontend and backend PR pair gets one review that catches a mismatch
in the eval.

## Later: more places, when people ask

The same product on other platforms; built when someone asks for one.

- GitLab
- Gitea and Forgejo
- Self-hosted GitHub App mode, built on the Phase 1 server

---

## Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-10-07 | Ship a GitHub Action first; the server becomes an optional self-hosted mode | Asking users to run Postgres, a server, ngrok and a webhook is too much friction |
| 2026-10-07 | Bring your own model key; no hosted multi-tenant SaaS for now | Solo project; avoids holding other people's code and paying their inference |
| 2026-10-07 | A repository's `.codemop.yml` controls review behaviour only, never the provider, model or endpoint, and is read from the default branch | Otherwise reviewing someone else's PR could send your API key to their server (or run up costs on an expensive model), and a PR could change how it's reviewed |
| 2026-10-07 | Also ship as a Claude Code plugin (skill + MCP server), instead of having CodeMop call a user's Claude subscription | Anthropic doesn't allow third-party products to offer claude.ai login or rate limits without approval; running inside Claude Code is the supported way for subscribers to use it |
| 2026-10-07 | Model agnostic: provider adapters behind one interface, selected by config; the default model is chosen by the comparison eval | Users have their own provider preferences, and quality differed noticeably between Le Chat and Claude in practice, so measure it rather than guess |
| 2026-10-07 | The original scope (`docs/archive/codemop_project_scope.md`, `docs/archive/epics.md`) is superseded | It was sized for a five-person team. Epic 1 → Phases 0–1; Epic 6 → Phases 2–3; Epic 3 → Phase 3 (suggestion blocks) and Phase 6 (grouped fixes); Epics 2, 4, 5, 7, 8 deferred |
| 2026-10-08 | Claude Opus 5.5 at high effort stays the default model; complexity-based routing is parked | The review eval: Opus did best on complex changes (17/20 against 14–15 for the alternatives), and reviews cost about two cents, so routing to cheaper models would save little |
| 2026-10-09 | Drop the Claude Code plugin | Claude Code has its own `/code-review`, and subscribers are reached the supported way by tiered review, which runs Anthropic's own `claude-code-action` as the deep tiers |
| 2026-10-09 | Grouped fixes you can apply, a review that learns from you, a merge check and repository context move into Phase 3 | They're the reasons to choose CodeMop over Claude's own reviews, so the Action should launch with them |
| 2026-10-09 | Repository context is on by default | With where the changed code is used, it found every cross-file bug in the eval (4/10 without), with no new false alarms, for about 13% more per review |
| 2026-10-09 | Routing comes back as tiered review: skip, CodeMop's diff review, or Claude Code's `/code-review` at low or high effort | Repository context matters, and the cost gap between a 2¢ diff review and an agentic review of the whole repository is large enough for a pre-judge to pay for itself |
| 2026-10-10 | The product design (`docs/product.md`) sets what comes after v1: TypeScript/JavaScript context and `codemop stats`, then `/codemop explain`, tiered review, and cross-repository review, as Phases 6–9; other platforms when asked | One product, the review loop for a change, rather than a bucket of features; smallest and widest first, so the big bets are chosen with real users' numbers |
| 2026-10-10 | Solo builders working with agents are a target, served by `/codemop explain` (teaching mode) | Nobody explains to them the code they ship; on demand, it costs other users nothing |
| 2026-10-10 | Cut multi-repository workspaces, the VS Code extension and the analytics dashboard | Workspaces are for writing code, not reviewing it (a separate project, if any); the PR already puts fixes one click away; a dashboard is against "everything happens on the PR" |
