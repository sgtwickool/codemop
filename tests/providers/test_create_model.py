import pytest

from codemop.providers import create_model
from codemop.providers.anthropic import AnthropicModel
from codemop.providers.openai_compatible import OpenAICompatibleModel


def test_anthropic_is_the_default():
    model = create_model()

    assert isinstance(model, AnthropicModel)
    assert model.name == "anthropic/claude-opus-5-5"


def test_mistral_has_a_default_model():
    model = create_model("mistral")

    assert isinstance(model, OpenAICompatibleModel)
    assert model.name == "mistral/codestral-latest"
    assert model.base_url == "https://api.mistral.ai/v1"


def test_ollama_uses_a_local_url():
    assert create_model("ollama", "qwen3-coder").base_url == "http://localhost:11434/v1"


def test_openai_compatible_takes_a_base_url_and_key_variable(monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret")

    model = create_model("openai-compatible", "my-model", base_url="http://vllm:8000/v1/", api_key_env="MY_KEY")

    assert model.base_url == "http://vllm:8000/v1"
    assert model.api_key == "secret"


@pytest.mark.parametrize("args, message", [
    (("openai",), "Name a model for openai"),
    (("openai-compatible", "m"), "needs a base URL"),
    (("gemini", "x"), "Unknown provider 'gemini'"),
])
def test_explains_what_is_missing(args, message):
    with pytest.raises(ValueError, match=message):
        create_model(*args)
