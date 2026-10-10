# Contributing

Thanks for helping. Issues and pull requests are welcome. For anything bigger than a fix,
open an issue first: the [product design](docs/product.md) says what CodeMop is for and the
rules it doesn't break, and the [roadmap](ROADMAP.md) what's planned.

## Setting up

```bash
git clone https://github.com/sgtwickool/codemop && cd codemop
python -m venv .venv && source .venv/bin/activate
pip install -e . --group dev
pytest
```

Python 3.12 or later. The tests need no API key, network or database: GitHub and the models are
replaced with fakes.

## Where things are

- `src/codemop/`: the package. `review/` turns a diff into checked suggestions (and repository
  context, fixes and learned notes), `providers/` has a module per model provider, `github/`
  talks to GitHub (inline comments, the summary, the merge check), and `cli/` has a module per
  command
- `action.yml`: the GitHub Action, which runs the `codemop` command
- `tests/`: mirrors `src/codemop/`. `tests/cli` runs the commands against a fake GitHub;
  `tests/golden` replays recorded model answers through the whole review
- `evals/review/`: the review eval
- `server/`: the optional [self-hosted webhook server](docs/self-hosting.md)

The [roadmap's layout](ROADMAP.md#repository-structure) has the full tree. A module that grows
past about 300 lines, or changes for two unrelated reasons, gets split.

## Making a change

1. Branch from `master` with a short, descriptive name in kebab-case, e.g. `context-callers` or
   `fix-crlf-ticks`
2. Add or update tests with the change. A golden test that changes on purpose is re-recorded
   with `CODEMOP_UPDATE_GOLDEN=1 pytest tests/golden`; check the new output by eye
3. Run `pytest`, and `ruff check --select F src tests evals` for unused or undefined names
   (`pip install ruff`, or `pipx run ruff ...`)
4. Open a pull request. CodeMop reviews it: deal with its findings the way the
   [README](README.md#responding-to-codemop) describes (tick the fix, resolve, or teach it), and
   it's merged once CI and CodeMop's merge check pass

Write commit messages and comments in plain English, saying what changed and why.

## Changing what the review finds

The instructions in `src/codemop/review/prompt.py`, the default model, repository context: a
change to any of them can make reviews better on one kind of change and worse on another, and
only the eval shows which. Run it before and after, and put the numbers in the pull request:

```bash
pytest evals/review/test_grading.py               # the grading, no API calls
export ANTHROPIC_API_KEY=...                       # spends money: about $2-4 a configuration
python evals/review/run.py --variant baseline
python evals/review/summarise.py
```

[`evals/review/README.md`](evals/review/README.md) explains the cases, the grading and the
results so far. New cases are welcome, especially real bugs from real pull requests.

## The server

```bash
pip install -e . -r server/requirements-dev.txt
cd server && pytest
```

Its tests use a temporary SQLite database and fixed settings (see `server/tests/conftest.py`).
After changing a model in `server/src/app/models/`, generate a migration, read it, and commit it:

```bash
cd server
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## Releasing

For maintainers. The version is in `src/codemop/__init__.py`.

1. Update the version and [CHANGELOG.md](CHANGELOG.md) in a pull request, and merge it
2. Tag the merge: `git tag v1.2.3 && git push origin v1.2.3`. The release workflow checks the tag
   matches the version, builds, and publishes to PyPI once a maintainer approves it in the
   `pypi` environment
3. Move the Action's major tag to the same commit, so `sgtwickool/codemop@v1` picks it up:
   `git tag -f v1 && git push -f origin v1`

## Reporting a security problem

Please don't open a public issue: see [SECURITY.md](SECURITY.md).
