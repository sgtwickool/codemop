import asyncio

import pytest

from codemop.github import api, files
from codemop.github.files import GitHubFiles


@pytest.fixture(autouse=True)
def no_snapshot(monkeypatch):
    """The repository is too large to download whole, unless a test says otherwise"""
    async def fetch_snapshot(repo, ref, **_):
        return None
    monkeypatch.setattr(api, "fetch_snapshot", fetch_snapshot)


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


@pytest.mark.asyncio
async def test_with_a_snapshot_every_file_comes_from_one_download(monkeypatch):
    downloads = []

    async def fetch_snapshot(repo, ref, **_):
        downloads.append(ref)
        return {"app.py": "x = 1\n", "lib/db.py": "y = 2\n"}
    monkeypatch.setattr(api, "fetch_snapshot", fetch_snapshot)
    monkeypatch.setattr(api, "fetch_repo_file", None)  # not called
    source = GitHubFiles("owner/repo", "abc", token=None, api_url="")

    assert await asyncio.gather(source.read("app.py"), source.read("missing.py"), source.paths()) == [
        "x = 1\n", None, ["app.py", "lib/db.py"]]
    assert downloads == ["abc"]
