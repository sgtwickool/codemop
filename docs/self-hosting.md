# Self-hosting the webhook server

CodeMop began as a server: a GitHub webhook sends it each pull request, it reviews the diff
with the `codemop` package, and it stores the suggestions in PostgreSQL, where an API serves
them. It doesn't post on the pull request; for that, and for fixes you can tick, use the
[GitHub Action](../README.md#quick-start-the-github-action), which needs no server at all.

The server suits setups where a webhook is easier than a workflow, or where you want the
suggestions in your own database. It's planned to become a self-hosted GitHub App (see the
[roadmap](../ROADMAP.md)).

## What you need

- Python 3.12 or later
- PostgreSQL 13 or later
- A public URL GitHub can reach (for trying it out, a tunnel such as [ngrok](https://ngrok.com/download))
- Docker, optionally

On Fedora, for example:

```bash
sudo dnf install python3 python3-pip postgresql-server postgresql-contrib
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
```

## Install and run

1. Clone the repository, and copy the settings: `cp .env.example .env`. The file explains each
   one. `GITHUB_WEBHOOK_SECRET` and `API_KEY` are required: the server won't start without them
   unless `APP_ENV=development` (which `.env.example` sets; unset, it's `production`)
2. Choose the model with `AI_PROVIDER`, `AI_MODEL`, `AI_BASE_URL` and `AI_API_KEY`, as for the
   Action (see [Choosing a model](../README.md#choosing-a-model))
3. Install the dependencies and set up the database (this creates `venv/`, and `.env` if it's
   missing): `./scripts/setup_dev.sh`
4. Start the server: `./scripts/run_dev.sh`

Or with Docker, the server and a database together: `docker compose up`. A production image is
built from `server/Dockerfile.prod`, and published to the GitHub Container Registry from
`master`:

```bash
docker build -f server/Dockerfile.prod -t codemop-server .
docker run -p 8000:8000 --env-file .env codemop-server
```

The server applies any pending database migrations when it starts.

## Connect GitHub

1. Expose the server, e.g. `ngrok http 8000`
2. In the repository: Settings → Webhooks → Add webhook
   - Payload URL: your URL plus `/api/v1/github/webhook` (e.g. `https://abc123.ngrok.io/api/v1/github/webhook`)
   - Content type: `application/json`
   - Secret: the same as `GITHUB_WEBHOOK_SECRET` in `.env`
   - Events: "Let me select individual events", then **Pull requests**
3. **Private repositories:** set `GITHUB_TOKEN` in `.env` so the server can fetch their diffs.
   Use a [fine-grained token](https://github.com/settings/personal-access-tokens/new) limited to
   the repositories you review, with read-only **Pull requests** and **Contents**. Public
   repositories work without one, but a token raises GitHub's rate limit from 60 to 5,000
   requests an hour
4. GitHub sends a `ping` when the webhook is created: its delivery log should show
   `"status": "pong"`. Then open a test pull request and check that delivery too

The repository's `.codemop.yml` applies here as it does for the Action.

## The API

All endpoints are under `/api/v1/`, with interactive docs at `/api/v1/docs`.

- `POST /api/v1/github/webhook`: GitHub's webhook
- `GET /api/v1/health`: a health check
- `GET /api/v1/repos/{owner}/{repo}/pulls/{number}/suggestions`: a pull request's suggestions
  (send `Authorization: Bearer <API_KEY>`)
- `GET /api/v1/pr/{pr_id}/suggestions`: the same, by the server's database id (the webhook
  response's `database_id`)

## Troubleshooting

- **Can't connect to the database:** check PostgreSQL is running (`sudo systemctl status
  postgresql`), that the database exists (`sudo -u postgres createdb codemop`), and that
  `DATABASE_URL` in `.env` is right
- **Port 8000 is in use:** find what has it with `lsof -i :8000`, or run on another port
- **A broken virtual environment:** `rm -rf venv`, then `./scripts/setup_dev.sh` again
- **Deliveries fail with 401:** the webhook's secret and `GITHUB_WEBHOOK_SECRET` don't match

Working on the server itself (its tests, and database migrations) is covered in
[CONTRIBUTING.md](../CONTRIBUTING.md#the-server).
