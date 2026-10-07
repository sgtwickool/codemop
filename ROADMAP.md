# CodeMop Roadmap

CodeMop reviews pull requests with AI and suggests fixes. The goal is a tool that is
useful day to day and that anyone can adopt in a couple of minutes, with no server to run.

This roadmap replaces the original scope documents in `docs/` (see [Decisions](#decisions)).
Phases are worked through in order. Each phase has a "done when" line, so it's clear when
to move on.

## How we work

- **Commit straight to `master`** while it's a solo project; CI must be green after every push.
  PRs come back once it's stable or someone else contributes.
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
- [ ] Keep dependencies current automatically (Dependabot, or a scheduled check)
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
- [ ] Check the "done when" end to end with a real PR and a real AI key, then tag `phase-1`

**Done when:** a real PR on a real (including private) repo gets stored suggestions,
with no GitHub delivery failures.

## Phase 2: Core package and CLI

Extract the review logic into a package that has nothing to do with FastAPI or the database.

- [ ] `codemop` core: diff → per-file chunks → prompt → model → validated suggestions
- [ ] Handle large diffs by chunking per file instead of cutting off at 10k characters; report anything skipped
- [ ] Map suggestions to diff positions (GitHub only accepts comments on lines in the diff)
- [ ] Config file `.codemop.yml`: model, ignored paths, minimum confidence, max comments
- [ ] CLI: `codemop review owner/repo#123 [--post] [--dry-run]`
- [ ] Golden tests from recorded diffs and model responses
- [ ] Move to the target [repository structure](#repository-structure): the package at the root, `backend/` becomes `server/` and uses it
- [ ] In the server, stop running synchronous database work inside `async` handlers and the background job (make DB-only handlers plain `def`, or move to async SQLAlchemy); it blocks the event loop under load
- [ ] Move the older integration tests' inline payloads and headers onto `tests/helpers.py` / the `post_webhook` fixture
- [ ] Publish to PyPI

### Model agnostic

Users bring their own provider and key, and review quality varies a lot between models,
so the core must not care which model it's talking to, and the choice of default must be measured.

- [ ] A single `ReviewModel` interface the rest of the code depends on; provider SDKs are imported only inside their adapters
- [ ] Adapters: Anthropic (official `anthropic` SDK, not an OpenAI-compatible shim, so structured output and refusal handling work properly), Mistral, and a generic OpenAI-compatible adapter (OpenAI, OpenRouter, local models through Ollama or vLLM)
- [ ] Each adapter uses its provider's native structured output (for Anthropic, `output_config.format` / `messages.parse()`). Every result is then validated against the same Pydantic schema, with one repair retry for providers that don't enforce a schema. Drop the plain-text scraping fallback
- [ ] Avoid provider-specific tricks that are going away: current Claude models reject both forced `tool_choice` and assistant-message prefill
- [ ] Treat non-answers as such: refusals, truncated output (`max_tokens`) and rate limits produce "no review, because …", and are never parsed as suggestions
- [ ] Model-aware token budgets: count tokens with each provider's own counter (for Anthropic, the `count_tokens` endpoint, not a tiktoken estimate) and size chunks to the model's context window
- [ ] Config: `provider`, `model`, `api_key_env`, optional `base_url`; no model IDs hardcoded outside the defaults
- [ ] Record tokens and estimated cost per run; use prompt caching where the provider supports it (the instructions are shared across every chunk of a PR)
- [ ] **Model comparison eval:** a fixed set of real PR diffs with known issues, scored the same way for every provider and model (real issues found, false positives, valid line positions, cost per useful comment). It picks the default and catches regressions when prompts or models change
- [ ] Choose the default model from the eval. Start by comparing Claude Opus 5.5 (`claude-opus-5-5`) against cheaper options, Codestral (the current default) and a local model

**Done when:** `pipx run codemop review sgtwickool/codemop#N --dry-run` prints useful suggestions
with at least two providers, and the eval results are in the repo.

## Phase 3: GitHub Action, and dogfooding

The main way people will use CodeMop.

- [ ] `action.yml` wrapping the CLI (`uses: sgtwickool/codemop@v1`), with `provider`, `model` and `api-key` inputs
- [ ] Post a single PR review with inline ```` ```suggestion ```` blocks (one-click apply) plus a summary
- [ ] Update the existing review on re-runs instead of piling up new ones
- [ ] Cost guardrails: maximum diff size and maximum number of comments
- [ ] Document permissions (`pull-requests: write`) and the limits on fork PRs (secrets aren't available there)
- [ ] Run it on CodeMop's own PRs for at least two weeks
- [ ] Tag `v1`; list on the GitHub Marketplace

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
- [ ] Pages: landing (pitch, demo GIF of a real review, two-minute setup), Quickstart, Configuration, Supported models, Privacy (exactly what code is sent where), Self-hosting, Changelog
- [ ] Deploy at `codemop.kempgt.com` (Vercel or GitHub Pages); link it from the CodeMop card on kempgt.com

**Done when:** the kempgt.com card links to a live site with a working quickstart.

## Phase 6: Later, maybe

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
| 2026-10-07 | Model agnostic: provider adapters behind one interface, selected by config; the default model is chosen by the comparison eval | Users have their own provider preferences, and quality differed noticeably between Le Chat and Claude in practice, so measure it rather than guess |
| 2026-10-07 | The original scope (`docs/codemop_project_scope.md`, `docs/epics.md`) is superseded | It was sized for a five-person team. Epic 1 → Phases 0–1; Epic 6 → Phases 2–3; Epic 3 → Phase 3 (suggestion blocks) and Phase 6 (grouped fixes); Epics 2, 4, 5, 7, 8 deferred |
