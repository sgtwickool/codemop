import pytest

from codemop.providers.anthropic import AnthropicModel
from codemop.providers.base import Usage
from codemop.providers.openai_compatible import OpenAICompatibleModel
from codemop.providers.pricing import ANTHROPIC_PRICES, Price


def test_cost_from_list_prices():
    # The real PR #2 review: 2,091 input and 440 output tokens on claude-opus-5-5
    cost = ANTHROPIC_PRICES["claude-opus-5-5"].cost(Usage(input_tokens=2091, output_tokens=440))

    assert cost == pytest.approx(0.017164)


def test_cache_tokens_are_priced():
    price = Price(input=4.0, output=20.0)  # no cache price given: a tenth of input

    assert price.cost(Usage(cache_read_tokens=1_000_000)) == pytest.approx(0.40)
    assert price.cost(Usage(cache_write_tokens=1_000_000)) == pytest.approx(5.00)


def test_each_adapter_estimates_its_own_cost():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)

    assert AnthropicModel("claude-sonnet-5-5", api_key="x").cost(usage) == pytest.approx(12.0)
    assert AnthropicModel("claude-made-up-9", api_key="x").cost(usage) is None
    assert OpenAICompatibleModel("qwen2.5-coder:7b", provider="ollama").cost(usage) == 0.0
    assert OpenAICompatibleModel("codestral-latest", provider="mistral", api_key="x").cost(usage) is None
