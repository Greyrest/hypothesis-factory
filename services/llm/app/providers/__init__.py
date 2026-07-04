"""Реестр LLM-провайдеров. Выбор — через env LLM_PROVIDER (anthropic|mock|none)."""
from __future__ import annotations

import os

from .base import LLMProvider


def get_provider() -> LLMProvider:
    name = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    if name == "mock":
        from .mock import MockProvider
        return MockProvider()
    from .base import NullProvider
    return NullProvider()
