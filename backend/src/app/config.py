from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings

# backend/src/app/config.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    # Application Configuration
    # Defaults are the safe choice for a deployment; .env.example sets up local development
    APP_ENV: str = "production"
    DEBUG: bool = False
    PORT: int = 8000

    # GitHub Webhook Configuration
    GITHUB_WEBHOOK_SECRET: str = ""

    # AI API Configuration
    AI_API_KEY: str = ""
    AI_API_URL: str = "https://api.mistral.ai/v1/chat/completions"
    AI_MODEL: str = "codestral-latest"

    # API Authentication
    API_KEY: str = ""

    # Database Configuration
    DATABASE_URL: str = "postgresql://codemop:codemop@localhost:5432/codemop"

    # Retry Configuration
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    model_config = {
        # Environment variables take precedence over the .env file
        'env_file': REPO_ROOT / '.env',
        'env_file_encoding': 'utf-8',
        'extra': 'allow'  # Allow extra environment variables
    }

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    def missing_secrets(self) -> List[str]:
        """Secrets that must be set for the server to be safe to expose"""
        return [
            name for name in ("GITHUB_WEBHOOK_SECRET", "API_KEY")
            if not getattr(self, name)
        ]

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
