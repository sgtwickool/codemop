"""
A pull request's files on GitHub, as of its head commit, for repository context. Reads are
best effort: a file that can't be read is simply left out of the context.
"""
from typing import Dict, List, Optional, Sequence

from codemop.github.client import GitHubError, fetch_repo_file, list_paths

MAX_READS = 30  # files read per review, so a large change can't make hundreds of requests


class GitHubFiles:
    def __init__(self, repo: str, ref: str, *, token: Optional[str], api_url: str):
        self.repo, self.ref, self.token, self.api_url = repo, ref, token, api_url
        self._texts: Dict[str, Optional[str]] = {}
        self._paths: Optional[List[str]] = None

    async def read(self, path: str) -> Optional[str]:
        if path not in self._texts:
            if len(self._texts) >= MAX_READS:
                return None
            try:
                self._texts[path] = await fetch_repo_file(self.repo, path, ref=self.ref, token=self.token,
                                                          api_url=self.api_url)
            except GitHubError:
                self._texts[path] = None
        return self._texts[path]

    async def paths(self) -> Sequence[str]:
        if self._paths is None:
            try:
                self._paths = await list_paths(self.repo, self.ref, token=self.token, api_url=self.api_url)
            except GitHubError:
                self._paths = []
        return self._paths
