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


def key_env(provider: str) -> Optional[str]:
    """The environment variable a provider's API key is read from by default (None: no key needed)"""
    if provider == "anthropic":
        return "ANTHROPIC_API_KEY"
    from codemop.providers.openai_compatible import PRESETS
    preset = PRESETS.get(provider)
    return preset.key_env if preset else None


def create_model(
    provider: str = "anthropic",
    model: Optional[str] = None,
    *,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    api_key_env: Optional[str] = None,
) -> ReviewModel:
    """
    The ReviewModel for a provider name (anthropic, mistral, openai, openrouter, ollama,
    openai-compatible). The API key is `api_key` if given, else read from `api_key_env`, else
    the provider's own variable (see key_env).
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}; choose one of: {', '.join(PROVIDERS)}")
    model = model or DEFAULT_MODELS.get(provider)
    if not model:
        raise ValueError(f"Name a model for {provider} (e.g. --model ...)")

    if provider == "anthropic":
        from codemop.providers.anthropic import AnthropicModel
        if not api_key and api_key_env:
            api_key = os.environ.get(api_key_env)
        return AnthropicModel(model, api_key=api_key)

    from codemop.providers.openai_compatible import OpenAICompatibleModel
    if provider == "openai-compatible" and not base_url:
        raise ValueError("openai-compatible needs a base URL (e.g. --base-url http://localhost:8000/v1)")
    return OpenAICompatibleModel(model, provider=provider, base_url=base_url, api_key=api_key, key_env=api_key_env)
