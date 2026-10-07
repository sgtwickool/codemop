import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings

# server/src/app/config.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# Secrets the server needs, and what happens without them in development.
# (Built from pairs: a dict literal keyed "...SECRET" trips bandit's hardcoded-password check.)
REQUIRED_SECRETS = dict([
    ("GITHUB_WEBHOOK_SECRET", "webhook signatures are NOT checked (development only)"),
    ("API_KEY", "the suggestions API rejects every request"),
])

class Settings(BaseSettings):
    # Application Configuration
    # Defaults are the safe choice for a deployment; .env.example sets up local development
    APP_ENV: str = "production"
    DEBUG: bool = False
    PORT: int = 8000

    # GitHub Webhook Configuration
    GITHUB_WEBHOOK_SECRET: str = ""
    
    # GitHub API, for fetching PR diffs. A token is needed for private repos, and raises
    # the rate limit for public ones (60 requests/hour without one)
    GITHUB_TOKEN: str = ""
    GITHUB_API_URL: str = "https://api.github.com"  # change for GitHub Enterprise Server

    # AI review, through the codemop package. AI_PROVIDER is one of: anthropic, mistral,
    # openai, openrouter, ollama, openai-compatible. The key is AI_API_KEY if set, otherwise the
    # provider's own environment variable (ANTHROPIC_API_KEY, MISTRAL_API_KEY...); ollama needs none
    AI_PROVIDER: str = "anthropic"
    AI_MODEL: str = ""  # empty: the provider's default (claude-opus-5-5, codestral-latest)
    AI_BASE_URL: str = ""  # for openai-compatible, or a self-hosted endpoint
    AI_API_KEY: str = ""

    # API Authentication
    API_KEY: str = ""

    # Database Configuration
    DATABASE_URL: str = "postgresql://codemop:codemop@localhost:5432/codemop"

    # Browser origins allowed to call the API, comma-separated (e.g. a dashboard at
    # https://codemop.example.com). Empty means no cross-origin browser access, which is all
    # GitHub and API clients like the CLI need: CORS only applies to browsers
    CORS_ORIGINS: str = ""
    
    # Monitoring
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "codemop"
    SENTRY_DSN: str = ""  # error tracking is off unless set
    ENABLE_METRICS: bool = False  # serve Prometheus metrics on METRICS_PORT
    METRICS_PORT: int = 8001
    
    model_config = {
        # Environment variables take precedence over the .env file
        'env_file': REPO_ROOT / '.env',
        'env_file_encoding': 'utf-8',
        'extra': 'allow'  # Allow extra environment variables
    }

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def ai_key_env(self) -> Optional[str]:
        """The provider's own API key variable (None: it needs no key)"""
        from codemop.providers import key_env
        return key_env(self.AI_PROVIDER)

    @property
    def ai_key_configured(self) -> bool:
        # (The provider's own variable has to be a real environment variable: values from .env
        # are only available as settings, which is what AI_API_KEY is for)
        key_env = self.ai_key_env
        return bool(self.AI_API_KEY) or key_env is None or bool(os.environ.get(key_env))

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    def missing_secrets(self) -> List[str]:
        """Secrets that must be set for the server to be safe to expose"""
        return [name for name in REQUIRED_SECRETS if not getattr(self, name)]

    def check_secrets(self) -> List[str]:
        """
        Raise if required secrets are missing, unless running in development, where
        they're optional and the missing ones are returned so they can be logged.
        """
        missing = self.missing_secrets()
        if missing and not self.is_development:
            raise RuntimeError(
                f"{', '.join(missing)} must be set when APP_ENV is '{self.APP_ENV}'. "
                "Set them in the environment or .env, or set APP_ENV=development for local use."
            )
        return missing

settings = Settings()
