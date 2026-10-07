"""
The parts of GitHub's pull_request webhook payload that CodeMop uses.

Payloads are validated against these after the signature check, so a malformed one is a
422 with the offending field named, not a 500 from the database. Fields GitHub sends that
aren't listed here are ignored.
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel


class GitHubUser(BaseModel):
    login: str


class GitHubBranch(BaseModel):
    ref: str
    sha: Optional[str] = None


class GitHubRepository(BaseModel):
    name: str
    full_name: str


class GitHubPullRequest(BaseModel):
    title: str
    user: GitHubUser
    head: GitHubBranch
    html_url: str
    state: str = "open"
    merged: bool = False
    draft: bool = False


class PullRequestEvent(BaseModel):
    action: str
    number: int
    pull_request: GitHubPullRequest
    repository: GitHubRepository

    @property
    def state(self) -> str:
        """open, closed or merged (GitHub reports merged PRs as closed)"""
        return "merged" if self.pull_request.merged else self.pull_request.state

    def pr_fields(self) -> Dict[str, Any]:
        """The values stored on the PR model"""
        return {
            "number": self.number,
            "repo_name": self.repository.name,
            "repo_full_name": self.repository.full_name,
            "branch": self.pull_request.head.ref,
            "author": self.pull_request.user.login,
            "title": self.pull_request.title,
            "status": self.state,
            "github_url": self.pull_request.html_url,
            "head_sha": self.pull_request.head.sha,
        }
