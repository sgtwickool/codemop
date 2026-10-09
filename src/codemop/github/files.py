"""
A pull request's files on GitHub, as of its head commit, for repository context: the whole
repository in one download when it's small enough (finding where changed code is used means
searching all of it), otherwise a file at a time. Reads are best effort: a file that can't be
read is simply left out of the context.
"""
import asyncio
from typing import Dict, List, Optional, Sequence

from codemop.github import api

MAX_READS = 30  # without the snapshot, files read per review, so a large change can't make hundreds of requests


class GitHubFiles:
    def __init__(self, repo: str, ref: str, *, token: Optional[str], api_url: str):
        self.repo, self.ref, self.token, self.api_url = repo, ref, token, api_url
        # Each fetched once, even when chunks reviewed at the same time ask for the same thing
        self._snapshot: Optional["asyncio.Task[Optional[Dict[str, str]]]"] = None
        self._reads: Dict[str, "asyncio.Task[Optional[str]]"] = {}
        self._paths: Optional["asyncio.Task[List[str]]"] = None

    async def read(self, path: str) -> Optional[str]:
        snapshot = await self.snapshot()
        if snapshot is not None:
            return snapshot.get(path)
        if path not in self._reads:
            if len(self._reads) >= MAX_READS:
                return None
            self._reads[path] = asyncio.ensure_future(self._fetch(path))
        return await self._reads[path]

    async def paths(self) -> Sequence[str]:
        snapshot = await self.snapshot()
        if snapshot is not None:
            return sorted(snapshot)
        if self._paths is None:
            self._paths = asyncio.ensure_future(self._list_paths())
        return await self._paths

    async def snapshot(self) -> Optional[Dict[str, str]]:
        if self._snapshot is None:
            self._snapshot = asyncio.ensure_future(
                api.fetch_snapshot(self.repo, self.ref, token=self.token, api_url=self.api_url))
        return await self._snapshot

    async def _fetch(self, path: str) -> Optional[str]:
        try:
            return await api.fetch_repo_file(self.repo, path, ref=self.ref, token=self.token, api_url=self.api_url)
        except api.GitHubError:
            return None

    async def _list_paths(self) -> List[str]:
        try:
            return await api.list_paths(self.repo, self.ref, token=self.token, api_url=self.api_url)
        except api.GitHubError:
            return []
