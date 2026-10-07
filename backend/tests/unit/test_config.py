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
