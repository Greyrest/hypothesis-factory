"""Реестр LLM-провайдеров.

Выбор — через env LLM_PROVIDER: anthropic | custom | mock | none.
custom (синонимы openai / openai_compat) — любой OpenAI-совместимый API:
свой ключ и адрес через LLM_API_KEY / LLM_BASE_URL, модель — LLM_MODEL.
"""
from __future__ import annotations

import os

from .base import LLMProvider


def get_provider() -> LLMProvider:
    name = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    if name in ("custom", "openai", "openai_compat", "openai-compat"):
        from .openai_compat import OpenAICompatProvider
        return OpenAICompatProvider()
    if name == "mock":
        from .mock import MockProvider
        return MockProvider()
    from .base import NullProvider
    return NullProvider()
