"""
A pull request's files on GitHub, as of its head commit, for repository context. Reads are
best effort: a file that can't be read is simply left out of the context.
"""
import asyncio
from typing import Dict, List, Optional, Sequence

from codemop.github import api

MAX_READS = 30  # files read per review, so a large change can't make hundreds of requests


class GitHubFiles:
    def __init__(self, repo: str, ref: str, *, token: Optional[str], api_url: str):
        self.repo, self.ref, self.token, self.api_url = repo, ref, token, api_url
        # Each read once, even when chunks reviewed at the same time ask for the same file
        self._reads: Dict[str, "asyncio.Task[Optional[str]]"] = {}
        self._paths: Optional["asyncio.Task[List[str]]"] = None

    async def read(self, path: str) -> Optional[str]:
        if path not in self._reads:
            if len(self._reads) >= MAX_READS:
                return None
            self._reads[path] = asyncio.ensure_future(self._fetch(path))
        return await self._reads[path]

    async def paths(self) -> Sequence[str]:
        if self._paths is None:
            self._paths = asyncio.ensure_future(self._list_paths())
        return await self._paths

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
