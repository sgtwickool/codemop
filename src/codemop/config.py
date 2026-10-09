"""
A repository's .codemop.yml: how its pull requests are reviewed.

It only controls review behaviour. Which provider and model run the review, and where
requests (and API keys) go, are decided by whoever runs CodeMop, never by the repository
being reviewed: otherwise reviewing someone else's PR could send your key to their server.
"""
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

CONFIG_FILE = ".codemop.yml"
DEFAULT_MIN_CONFIDENCE = 0.5


class ConfigError(Exception):
    """.codemop.yml couldn't be used; the message says what's wrong with it"""


class RepoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ignore: List[str] = Field(
        default_factory=list,
        description="Path patterns not to review, in addition to the defaults (lock files, minified files...)",
    )
    min_confidence: float = Field(
        default=DEFAULT_MIN_CONFIDENCE, ge=0, le=1,
        description="Drop suggestions the model is less sure of than this",
    )
    chunk_tokens: Optional[int] = Field(
        default=None, ge=1000,
        description="Largest piece of diff sent in one request (default: the model's own)",
    )
    max_comments: int = Field(
        default=10, ge=1, le=50,
        description="Most inline comments in a posted review; the rest are listed in its summary",
    )


def parse_config(text: str, source: str = CONFIG_FILE) -> RepoConfig:
    """Read a .codemop.yml; an empty file means all defaults"""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError(f"{source} isn't valid YAML: {e}")
    if data is None:
        return RepoConfig()
    if not isinstance(data, dict):
        raise ConfigError(f"{source} should be a mapping of settings, like `min_confidence: 0.6`")
    try:
        return RepoConfig.model_validate(data)
    except ValidationError as e:
        problems = []
        for error in e.errors():
            field = ".".join(str(part) for part in error["loc"]) or "(top level)"
            if error["type"] == "extra_forbidden":
                problems.append(f"unknown setting `{field}` (settings: {', '.join(RepoConfig.model_fields)})")
            else:
                problems.append(f"`{field}`: {error['msg']}")
        raise ConfigError(f"{source}: " + "; ".join(problems))


def load_config_file(path: Path) -> Optional[RepoConfig]:
    """The config at `path`, or None if there's no such file"""
    if not path.is_file():
        return None
    return parse_config(path.read_text(), source=str(path))
