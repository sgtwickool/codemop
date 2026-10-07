"""
Model providers, one module each, behind the interface in providers.base.

create_model() is the one place that knows which providers exist.
"""
import os
from typing import Optional

from codemop.providers.base import ReviewModel

PROVIDERS = ("anthropic", "mistral", "openai", "openrouter", "ollama", "openai-compatible")

# Providers with a sensible default model; the rest need one named
DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "mistral": "codestral-latest",
}


def create_model(
    provider: str = "anthropic",
    model: Optional[str] = None,
    *,
    base_url: Optional[str] = None,
    api_key_env: Optional[str] = None,
) -> ReviewModel:
    """The ReviewModel for a provider name (anthropic, mistral, openai, openrouter, ollama, openai-compatible)"""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}; choose one of: {', '.join(PROVIDERS)}")
    model = model or DEFAULT_MODELS.get(provider)
    if not model:
        raise ValueError(f"Name a model for {provider} (e.g. --model ...)")

    if provider == "anthropic":
        from codemop.providers.anthropic import AnthropicModel
        api_key = os.environ.get(api_key_env) if api_key_env else None
        return AnthropicModel(model, api_key=api_key)

    from codemop.providers.openai_compatible import OpenAICompatibleModel
    if provider == "openai-compatible" and not base_url:
        raise ValueError("openai-compatible needs a base URL (e.g. --base-url http://localhost:8000/v1)")
    return OpenAICompatibleModel(model, provider=provider, base_url=base_url, key_env=api_key_env)
