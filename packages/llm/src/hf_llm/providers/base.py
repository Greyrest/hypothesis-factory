"""Контракт LLM-провайдера и типы результата."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMUsage:
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0


@dataclass
class StructuredCompletion:
    """Валидный JSON-ответ модели по переданной схеме + телеметрия."""
    data: dict
    usage: LLMUsage


class LLMError(Exception):
    """Базовая ошибка LLM-слоя."""


class LLMUnavailable(LLMError):
    """Провайдер недоступен (нет ключа/сети)."""


class LLMRefusal(LLMError):
    """Модель отказалась отвечать."""


class LLMBadOutput(LLMError):
    """Ответ не удалось разобрать по схеме."""


class LLMProvider(Protocol):
    def available(self) -> bool: ...

    def complete_structured(self, *, system: str, user: str, schema: dict,
                            max_tokens: int) -> StructuredCompletion: ...
