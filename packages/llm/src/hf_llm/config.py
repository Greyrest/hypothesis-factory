"""Конфигурация LLM-слоя."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LLMConfig(BaseModel):
    provider: Literal["anthropic", "mock"] = "anthropic"
    model: str = "claude-opus-4-8"
    max_tokens: int = 16000
    thinking: Literal["adaptive", "off"] = "adaptive"
    timeout_s: float = 120.0
    enabled: bool = True
    # для provider="mock" (тесты и офлайн-демо): готовый ответ модели
    mock_response: dict | None = None
