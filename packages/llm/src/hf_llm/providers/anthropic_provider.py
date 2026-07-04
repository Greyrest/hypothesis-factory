"""Провайдер Anthropic (перенос вызова из прототипа generate.llm_enhance)."""
from __future__ import annotations

import json
import os
import time

from hf_llm.config import LLMConfig
from hf_llm.providers.base import (
    LLMBadOutput,
    LLMRefusal,
    LLMUnavailable,
    LLMUsage,
    StructuredCompletion,
)


class AnthropicProvider:
    def __init__(self, config: LLMConfig):
        self._config = config

    def available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def complete_structured(self, *, system: str, user: str, schema: dict,
                            max_tokens: int) -> StructuredCompletion:
        if not self.available():
            raise LLMUnavailable("ANTHROPIC_API_KEY не задан")
        import anthropic

        client = anthropic.Anthropic(timeout=self._config.timeout_s)
        kwargs: dict = {}
        if self._config.thinking == "adaptive":
            kwargs["thinking"] = {"type": "adaptive"}

        t0 = time.monotonic()
        msg = client.messages.create(
            model=self._config.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
            **kwargs,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        if msg.stop_reason == "refusal":
            raise LLMRefusal("модель отказалась отвечать")
        text = next((b.text for b in msg.content if b.type == "text"), None)
        if text is None:
            raise LLMBadOutput("в ответе нет текстового блока")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMBadOutput(f"невалидный JSON: {e}") from e

        usage = getattr(msg, "usage", None)
        return StructuredCompletion(
            data=data,
            usage=LLMUsage(
                model=self._config.model,
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                latency_ms=latency_ms,
            ),
        )
