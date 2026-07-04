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

    def translate(self, texts: list[str], lang: str) -> list[str] | None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        lang_name = {"en": "английский", "zh": "китайский"}.get(lang, lang)
        schema = {"type": "object",
                  "properties": {"translations": {
                      "type": "array", "items": {"type": "string"}}},
                  "required": ["translations"], "additionalProperties": False}
        try:
            import anthropic
            client = anthropic.Anthropic()
            msg = client.messages.create(
                model=self.model,
                max_tokens=32000,
                system=(f"Переведи каждый элемент массива на {lang_name} язык. "
                        "Технические термины обогащения руд переводи корректно, "
                        "Markdown-разметку, числа и единицы сохраняй как есть. "
                        "Верни массив той же длины."),
                messages=[{"role": "user",
                           "content": json.dumps(texts, ensure_ascii=False)}],
                output_config={"format": {"type": "json_schema",
                                          "schema": schema}},
            )
            if msg.stop_reason == "refusal":
                return None
            text = next(b.text for b in msg.content if b.type == "text")
            out = json.loads(text)["translations"]
            return out if len(out) == len(texts) else None
        except Exception as e:
            print(f"[LLM translate] пропущено: {type(e).__name__}: {e}")
            return None
