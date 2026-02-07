import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Application Configuration
    APP_ENV: str = "development"
    DEBUG: bool = True
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
    
    class Config:
        env_file = "/home/sgtwickool/repos/codemop/.env"
        env_file_encoding = 'utf-8'

settings = Settings()