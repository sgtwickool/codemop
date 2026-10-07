# CodeMop Roadmap

CodeMop reviews pull requests with AI and suggests fixes. The goal is a tool that is
useful day to day and that anyone can adopt in a couple of minutes, with no server to run.

This roadmap replaces the original scope documents in `docs/` (see [Decisions](#decisions)).
Phases are worked through in order. Each phase has a "done when" line, so it's clear when
to move on.

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
- [ ] Identify a PR by `(repo_full_name, number)`, not the PR number alone (PRs in different repos currently overwrite each other)
- [ ] Upsert PRs, and de-duplicate deliveries by `X-GitHub-Delivery` (handles retries and concurrent duplicates)
- [ ] Return from the webhook within 1s; run analysis in the background
- [ ] Analyse only on `opened`, `synchronize`, `reopened` and `ready_for_review`; replace old suggestions per head SHA
- [ ] Store PR state (open/closed/merged), not the last webhook action
- [ ] Refuse to start without `GITHUB_WEBHOOK_SECRET` and `API_KEY` (outside dev); compare keys in constant time
- [ ] Validate signatures on every event, not just `pull_request`
- [ ] Fetch diffs with a GitHub token so private repos work
- [ ] Look up suggestions by repo + PR number
- [ ] Rethink the webhook rate limit (10/min drops legitimate bursts, and GitHub doesn't retry a 429)
- [ ] Fix Prometheus metrics (the middleware binds `None` at import); turn the metrics server off by default
- [ ] Replace `print` with logging; tighten CORS (no wildcard with credentials)

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
