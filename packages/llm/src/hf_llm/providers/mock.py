"""Мок-провайдер: детерминированный ответ из конфигурации (тесты, демо)."""
from __future__ import annotations

from hf_llm.config import LLMConfig
from hf_llm.providers.base import LLMUnavailable, LLMUsage, StructuredCompletion


class MockProvider:
    def __init__(self, config: LLMConfig):
        self._config = config

    def available(self) -> bool:
        return self._config.mock_response is not None

    def complete_structured(self, *, system: str, user: str, schema: dict,
                            max_tokens: int) -> StructuredCompletion:
        if self._config.mock_response is None:
            raise LLMUnavailable("mock_response не задан")
        return StructuredCompletion(
            data=self._config.mock_response,
            usage=LLMUsage(model="mock", input_tokens=len(user) // 4,
                           output_tokens=0, latency_ms=0),
        )
