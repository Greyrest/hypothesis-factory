"""hf_llm — универсальный слой работы с языковыми моделями (ТЗ §10).

Отвечает ТОЛЬКО за: вызов провайдера, структурированный вывод по JSON-схеме,
обработку ошибок с гарантированным fallback (None -> rule-based режим),
телеметрию. Никакой доменной бизнес-логики: промпты и схемы конкретных
доменов живут в адаптерах hf_domains и передаются сюда параметрами.
"""
from hf_llm.config import LLMConfig
from hf_llm.providers.base import (
    LLMBadOutput,
    LLMError,
    LLMProvider,
    LLMRefusal,
    LLMUnavailable,
    LLMUsage,
    StructuredCompletion,
)
from hf_llm.usecases.structured import get_provider, run_structured

__all__ = [
    "LLMConfig",
    "run_structured", "get_provider",
    "LLMProvider", "StructuredCompletion", "LLMUsage",
    "LLMError", "LLMUnavailable", "LLMRefusal", "LLMBadOutput",
]
