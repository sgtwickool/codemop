"""
Tests for settings validation: the server must not run without its secrets, except in
development.
"""
import pytest

from app.config import Settings


def make_settings(**values) -> Settings:
    # _env_file=None: ignore any .env file, so only the values given here count
    return Settings(_env_file=None, **values)


def test_defaults_are_production_safe(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    settings = make_settings()

    assert settings.APP_ENV == "production"
    assert settings.DEBUG is False


@pytest.mark.parametrize("app_env", ["production", "staging", "test"])
def test_missing_secrets_stop_startup_outside_development(app_env):
    settings = make_settings(APP_ENV=app_env, GITHUB_WEBHOOK_SECRET="", API_KEY="")

    with pytest.raises(RuntimeError) as error:
        settings.check_secrets()

    assert "GITHUB_WEBHOOK_SECRET, API_KEY must be set" in str(error.value)


def test_one_missing_secret_is_named():
    settings = make_settings(APP_ENV="production", GITHUB_WEBHOOK_SECRET="set", API_KEY="")

    with pytest.raises(RuntimeError, match="^API_KEY must be set"):
        settings.check_secrets()


def test_secrets_are_optional_in_development():
    settings = make_settings(APP_ENV="development", GITHUB_WEBHOOK_SECRET="", API_KEY="")

    assert settings.check_secrets() == ["GITHUB_WEBHOOK_SECRET", "API_KEY"]


def test_configured_secrets_pass():
    settings = make_settings(APP_ENV="production", GITHUB_WEBHOOK_SECRET="s", API_KEY="k")

    assert settings.check_secrets() == []


def test_review_model_follows_the_ai_settings(monkeypatch):
    from unittest.mock import patch
    from app.config import settings
    from app.services import pr_analysis

    monkeypatch.setattr(settings, "AI_PROVIDER", "openai-compatible")
    monkeypatch.setattr(settings, "AI_MODEL", "my-model")
    monkeypatch.setattr(settings, "AI_BASE_URL", "http://vllm:8000/v1")
    monkeypatch.setattr(settings, "AI_API_KEY", "server-key")

    with patch("app.services.pr_analysis.create_model") as create_model:
        pr_analysis.review_model()

    create_model.assert_called_once_with(
        "openai-compatible", "my-model", base_url="http://vllm:8000/v1", api_key="server-key"
    )


def test_review_model_leaves_unset_values_to_the_provider_defaults(monkeypatch):
    from unittest.mock import patch
    from app.config import settings
    from app.services import pr_analysis

    for name, value in {"AI_PROVIDER": "anthropic", "AI_MODEL": "", "AI_BASE_URL": "", "AI_API_KEY": ""}.items():
        monkeypatch.setattr(settings, name, value)

    with patch("app.services.pr_analysis.create_model") as create_model:
        pr_analysis.review_model()

    create_model.assert_called_once_with("anthropic", None, base_url=None, api_key=None)


@pytest.mark.parametrize("provider, key, env, configured", [
    ("anthropic", "", {}, False),
    ("anthropic", "k", {}, True),
    ("anthropic", "", {"ANTHROPIC_API_KEY": "from-env"}, True),
    ("ollama", "", {}, True),  # local: no key needed
])
def test_ai_key_configured(monkeypatch, provider, key, env, configured):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    settings = make_settings(AI_PROVIDER=provider, AI_API_KEY=key)

    assert settings.ai_key_configured is configured
