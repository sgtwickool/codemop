"""
.codemop.yml: review settings for a repository.
"""
import pytest

from codemop.config import ConfigError, RepoConfig, load_config_file, parse_config


def test_empty_file_means_defaults():
    assert parse_config("") == RepoConfig()
    assert RepoConfig().min_confidence == 0.5


def test_reads_the_settings():
    config = parse_config("ignore:\n  - 'docs/*'\n  - '*.snap'\nmin_confidence: 0.7\nchunk_tokens: 20000\n")

    assert config.ignore == ["docs/*", "*.snap"]
    assert config.min_confidence == 0.7
    assert config.chunk_tokens == 20000


@pytest.mark.parametrize("text, message", [
    ("provider: openai-compatible\nbase_url: https://elsewhere", "unknown setting `provider`"),
    ("min_confidence: 2", "`min_confidence`: Input should be less than or equal to 1"),
    ("chunk_tokens: 10", "`chunk_tokens`: Input should be greater than or equal to 1000"),
    ("ignore: [unclosed", "isn't valid YAML"),
    ("- just\n- a list", "should be a mapping of settings"),
])
def test_problems_are_explained(text, message):
    with pytest.raises(ConfigError) as error:
        parse_config(text, source="owner/repo/.codemop.yml")

    assert str(error.value).startswith("owner/repo/.codemop.yml")
    assert message in str(error.value)


def test_a_repository_cant_choose_the_model_or_where_requests_go():
    """Otherwise reviewing someone else's PR could send your API key to their server"""
    for setting in ("provider", "model", "base_url", "api_key_env"):
        with pytest.raises(ConfigError, match=f"unknown setting `{setting}`"):
            parse_config(f"{setting}: x")


def test_load_config_file(tmp_path):
    assert load_config_file(tmp_path / ".codemop.yml") is None
    (tmp_path / ".codemop.yml").write_text("min_confidence: 0.8\n")

    assert load_config_file(tmp_path / ".codemop.yml").min_confidence == 0.8
