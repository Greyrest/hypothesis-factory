"""Единственный use case ядра: структурированная задача по JSON-схеме.

Доменные use cases (enhance_hypotheses, generate_from_context, explain,
summarize_sources, translate) — это конкретные (system, context, schema),
которые собирает вызывающая сторона; здесь — вызов, fallback и телеметрия.
Любая ошибка => None: конвейер обязан продолжать работу в rule-based режиме.
"""
from __future__ import annotations

import json
import logging

from hf_llm.config import LLMConfig
from hf_llm.providers.anthropic_provider import AnthropicProvider
from hf_llm.providers.base import LLMProvider, StructuredCompletion
from hf_llm.providers.mock import MockProvider

logger = logging.getLogger("hf_llm")


def get_provider(config: LLMConfig) -> LLMProvider:
    if config.provider == "mock":
        return MockProvider(config)
    return AnthropicProvider(config)


def run_structured(*, task: str, system: str, context: dict | str,
                   schema: dict, config: LLMConfig) -> StructuredCompletion | None:
    """Выполнить структурированную LLM-задачу. None => остаёмся на rule-based."""
    if not config.enabled:
        return None
    provider = get_provider(config)
    if not provider.available():
        logger.info("[LLM] %s: провайдер %s недоступен — пропущено",
                    task, config.provider)
        return None

    user = context if isinstance(context, str) else json.dumps(
        context, ensure_ascii=False)
    try:
        result = provider.complete_structured(
            system=system, user=user, schema=schema,
            max_tokens=config.max_tokens)
    except Exception as e:  # сеть/ключ/квота/схема — не роняем конвейер
        logger.warning("[LLM] %s пропущено: %s: %s", task, type(e).__name__, e)
        return None

    u = result.usage
    logger.info("[LLM] %s: ok model=%s in=%s out=%s %dms",
                task, u.model, u.input_tokens, u.output_tokens, u.latency_ms)
    return result
