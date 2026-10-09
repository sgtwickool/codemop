import asyncio

import pytest

from codemop.github import api, files
from codemop.github.files import GitHubFiles


@pytest.mark.asyncio
async def test_a_file_asked_for_at_the_same_time_is_read_once(monkeypatch):
    """Chunks are reviewed at the same time, and often want the same file"""
    reads = []

    async def fetch_repo_file(repo, path, **_):
        reads.append(path)
        await asyncio.sleep(0)
        return f"text of {path}"
    monkeypatch.setattr(api, "fetch_repo_file", fetch_repo_file)
    source = GitHubFiles("owner/repo", "abc", token=None, api_url="")

    texts = await asyncio.gather(source.read("app.py"), source.read("app.py"), source.read("db.py"))

    assert texts == ["text of app.py", "text of app.py", "text of db.py"]
    assert reads == ["app.py", "db.py"]


@pytest.mark.asyncio
async def test_reads_are_best_effort_and_limited(monkeypatch):
    async def fetch_repo_file(repo, path, **_):
        if path == "secret.py":
            raise api.GitHubError("GitHub returned 403", 403)
        return "x"
    monkeypatch.setattr(api, "fetch_repo_file", fetch_repo_file)
    monkeypatch.setattr(files, "MAX_READS", 2)
    source = GitHubFiles("owner/repo", "abc", token=None, api_url="")

    assert await source.read("secret.py") is None
    assert await source.read("a.py") == "x"
    assert await source.read("b.py") is None  # over the limit
    assert await source.read("a.py") == "x"  # already read
