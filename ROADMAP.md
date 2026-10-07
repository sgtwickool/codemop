# CodeMop Roadmap

CodeMop reviews pull requests with AI and suggests fixes. The goal is a tool that is
useful day to day and that anyone can adopt in a couple of minutes, with no server to run.

This roadmap replaces the original scope documents in `docs/` (see [Decisions](#decisions)).
Phases are worked through in order. Each phase has a "done when" line, so it's clear when
to move on.

## How we work

- **Commit straight to `master`** while it's a solo project; CI must be green after every push.
  Our own PRs start after Phase 4 or 5, once the product is in better shape. Dependabot's
  monthly update PRs are the exception: review and merge them as they come.
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

Today everything is the webhook server, under `backend/`. Phase 2 moves to this layout, when
the review logic becomes its own package:

```
codemop/
├── action.yml            # the GitHub Action (it must be at the root for `uses: sgtwickool/codemop@v1`)
├── pyproject.toml        # the `codemop` package (core + CLI), published to PyPI
├── src/codemop/
│   ├── review/           # diff -> per-file chunks -> prompt -> validated suggestions
│   ├── providers/        # one module per model provider, behind one interface
│   ├── github/           # GitHub API client: fetch diffs, post reviews
│   └── cli.py
├── tests/                # tests for the package, mirroring src/codemop/
├── server/               # the optional self-hosted webhook server (today's backend/), using the package
├── site/                 # Astro + Starlight marketing and docs site (Phase 5)
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
(Phase 6). Analysis-quality and model-provider work moves to the shared core in Phase 2;
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
- [ ] Config file `.codemop.yml`: model, ignored paths, minimum confidence, max comments
- [x] CLI: `codemop review owner/repo#123` (or a PR URL, or `-` for a diff on stdin) prints the review; `--json` for machines. Posting comes with `--post` in Phase 3. Uses `GITHUB_TOKEN`, or the `gh` login, for private repos
- [ ] Golden tests from recorded diffs and model responses
- [ ] Move to the target [repository structure](#repository-structure): the package at the root, `backend/` becomes `server/` and uses it
- [ ] In the server, stop running synchronous database work inside `async` handlers and the background job (make DB-only handlers plain `def`, or move to async SQLAlchemy); it blocks the event loop under load
- [ ] Move the older integration tests' inline payloads and headers onto `tests/helpers.py` / the `post_webhook` fixture
- [ ] Publish to PyPI

### Model agnostic

Users bring their own provider and key, and review quality varies a lot between models,
so the core must not care which model it's talking to, and the choice of default must be measured.

- [x] A single `ReviewModel` interface the rest of the code depends on; provider SDKs are imported only inside their adapters
- [x] Adapters: Anthropic (official `anthropic` SDK, not an OpenAI-compatible shim, so structured output and refusal handling work properly), and one OpenAI-compatible adapter that covers Mistral (its API is OpenAI-compatible, structured output included), OpenAI, OpenRouter and local models through Ollama or vLLM
- [x] Each adapter uses its provider's native structured output (for Anthropic, `output_config.format` / `messages.parse()`). Every result is then validated against the same Pydantic schema, with one repair retry for providers that don't enforce a schema. Drop the plain-text scraping fallback
- [x] Avoid provider-specific tricks that are going away: current Claude models reject both forced `tool_choice` and assistant-message prefill (structured output instead)
- [x] Treat non-answers as such: refusals, truncated output (`max_tokens`), rate limits and a rejected API key produce "no review, because …" (saying what to fix, like the GitHub errors do), and are never parsed as suggestions
- [x] Token budgets: chunks are planned with a deliberately high estimate (3 characters per token), so they're never too big for `chunk_tokens`; real usage comes back on every response. (Counting exactly with each provider's endpoint would cost an API call per file and hunk while planning)
- [ ] Config: `provider`, `model`, `api_key_env`, optional `base_url`; no model IDs hardcoded outside the defaults
- [ ] Record tokens and estimated cost per run. (Prompt caching doesn't help yet: the shared instructions are a few hundred tokens, below Claude's minimum cacheable prefix of 1,024+)
- [ ] **Model comparison eval:** a fixed set of real PR diffs with known issues, scored the same way for every provider and model (real issues found, false positives, valid line positions, cost per useful comment). It picks the default, catches regressions when prompts or models change, and later measures complexity-based routing (Phase 6)
- [ ] End-to-end check carried over from Phase 1: a real PR through the server with Claude ends with stored suggestions
- [ ] Choose the default model from the eval. Start by comparing Claude Opus 5.5 (`claude-opus-5-5`) against cheaper options, Codestral (the current default) and a local model

**Done when:** `pipx run codemop review sgtwickool/codemop#N` prints useful suggestions
with at least two providers, and the eval results are in the repo.

## Phase 3: GitHub Action, Claude Code plugin, and dogfooding

The two ways people will use CodeMop: a GitHub Action with an API key for any provider, and a
Claude Code plugin for people who already pay for Claude. Both build on the same core and the
same review-posting code.

### GitHub Action

- [ ] `action.yml` wrapping the CLI (`uses: sgtwickool/codemop@v1`), with `provider`, `model` and `api-key` inputs
- [ ] Post a single PR review with inline ```` ```suggestion ```` blocks (one-click apply) plus a summary
- [ ] Update the existing review on re-runs instead of piling up new ones
- [ ] Cost guardrails: maximum diff size and maximum number of comments
- [ ] Document permissions (`pull-requests: write`) and the limits on fork PRs (secrets aren't available there)
- [ ] Run it on CodeMop's own PRs for at least two weeks
- [ ] Tag `v1`; list on the GitHub Marketplace

### Claude Code plugin

Runs inside the user's own Claude Code session, on their own subscription: Claude Code does the
reviewing, CodeMop supplies the method and the tools. CodeMop never handles the user's login.

- [ ] MCP server exposing the core as tools: fetch a PR's diff in chunks, check suggestions against the lines GitHub can comment on, post the review
- [ ] A skill with CodeMop's review instructions, so `/codemop review owner/repo#N` works in Claude Code
- [ ] A workflow recipe for Anthropic's `claude-code-action` (with a `claude setup-token` token), so CI reviews can run on a Pro/Max subscription
- [ ] Publish it to a plugin marketplace
- [ ] Before promoting "works with your Claude subscription": check Anthropic's current terms (third-party products may not offer claude.ai login or rate limits unless approved), and ask Anthropic if in doubt

**What it has to do better than Claude Code's own PR reviews:** suggestions placed on exactly the
right lines, one-click "suggested change" blocks, grouped fixes, and a choice of models (via the
Action).

**Done when:** someone else installs it from the README alone and it reviews their PR.

## Phase 4: Docs cleanup

- [ ] Rewrite the README around the Action quickstart; move server setup to a self-hosting doc
- [ ] `CONTRIBUTING.md` (dev setup, tests, branch naming)
- [ ] `SECURITY.md` (how to report issues, plus the accepted risks from `SECURITY_DECISIONS.md`)
- [ ] `CHANGELOG.md`
- [ ] Archive the original scope and epics to `docs/archive/`; delete or archive the local process docs (`PHASE_1_IMPLEMENTATION.md`, `BRANCH_STRATEGY_UPDATE.md`, `CI_CD_ROLLOUT_PLAN.md`, `STEERING.md`, `TESTING_GUIDE.md`, `backend/docs/`)

## Phase 5: Website (marketing and docs)

- [ ] Astro + Starlight site in `site/`, so the docs are versioned with the code
- [ ] Match the look of kempgt.com (fonts, palette) and reuse the animated `mop()` print
- [ ] Pages: landing (pitch, demo GIF of a real review, two-minute setup), Quickstart (the Action and the Claude Code plugin), Configuration, Supported models, Privacy (exactly what code is sent where), Self-hosting, Changelog
- [ ] Deploy at `codemop.kempgt.com` (Vercel or GitHub Pages); link it from the CodeMop card on kempgt.com

**Done when:** the kempgt.com card links to a live site with a working quickstart.

## Phase 6: Later, maybe

- **Complexity-based routing** (needs the Phase 2 eval to tune and trust it). Route each chunk,
  not the whole PR, to the cheapest review that's good enough:
  1. Free checks first, with no model: skip only what's certainly trivial (docs-only, lock
     files, pure renames, whitespace); send obviously risky code (auth, crypto, SQL and
     migrations, concurrency, payments, large logic changes) straight to the strong tier
  2. A cheap model triages the rest and picks the cheap or the strong reviewer. It never skips
     a review: a "trivial" call on a subtle bug is the failure to avoid
  3. Compare against routing by effort level on one model (e.g. Claude Opus at low effort for
     simple chunks), which is often as good and cheaper, with one model to keep consistent
  4. The report says which model reviewed each part, and why anything was skipped. Success is
     measured by the eval: issues missed against reviewing everything with the strong model,
     and the cost saved
  5. Tiers configurable in `.codemop.yml`
- **Grouped fixes:** related issues bundled into one suggestion/commit (the main differentiator)
- **Self-hosted GitHub App mode**, built on the Phase 1 server
- GitLab support
- VS Code extension and team analytics dashboard (low priority; the suggestion blocks in Phase 3 cover most of the value)

---

## Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-10-07 | Ship a GitHub Action first; the server becomes an optional self-hosted mode | Asking users to run Postgres, a server, ngrok and a webhook is too much friction |
| 2026-10-07 | Bring your own model key; no hosted multi-tenant SaaS for now | Solo project; avoids holding other people's code and paying their inference |
| 2026-10-07 | Also ship as a Claude Code plugin (skill + MCP server), instead of having CodeMop call a user's Claude subscription | Anthropic doesn't allow third-party products to offer claude.ai login or rate limits without approval; running inside Claude Code is the supported way for subscribers to use it |
| 2026-10-07 | Model agnostic: provider adapters behind one interface, selected by config; the default model is chosen by the comparison eval | Users have their own provider preferences, and quality differed noticeably between Le Chat and Claude in practice, so measure it rather than guess |
| 2026-10-07 | The original scope (`docs/codemop_project_scope.md`, `docs/epics.md`) is superseded | It was sized for a five-person team. Epic 1 → Phases 0–1; Epic 6 → Phases 2–3; Epic 3 → Phase 3 (suggestion blocks) and Phase 6 (grouped fixes); Epics 2, 4, 5, 7, 8 deferred |
