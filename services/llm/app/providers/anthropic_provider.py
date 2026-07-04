"""Провайдер Anthropic Claude (structured output по HYP_SCHEMA).

Модель задаётся env LLM_MODEL (по умолчанию claude-opus-4-8) — замена модели
не требует изменений кода других сервисов.
"""
from __future__ import annotations

import json
import os

from ..schema import HYP_SCHEMA, SYSTEM_PROMPT
from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self):
        self.model = os.environ.get("LLM_MODEL", "claude-opus-4-8")

    def enhance(self, context: dict) -> list[dict] | None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic
            client = anthropic.Anthropic()
            msg = client.messages.create(
                model=self.model,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user",
                           "content": json.dumps(context, ensure_ascii=False)}],
                output_config={"format": {"type": "json_schema",
                                          "schema": HYP_SCHEMA}},
            )
            if msg.stop_reason == "refusal":
                return None
            text = next(b.text for b in msg.content if b.type == "text")
            return json.loads(text)["hypotheses"]
        except Exception as e:  # сеть/ключ/квота — не роняем конвейер
            print(f"[LLM] пропущено: {type(e).__name__}: {e}")
            return None
