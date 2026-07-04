"""Универсальный провайдер: любой OpenAI-совместимый Chat Completions API.

Формат /chat/completions — стандарт де-факто: его поддерживают DeepSeek, Qwen,
Mistral, OpenRouter, Together, а также локальные Ollama / vLLM / LM Studio.
Точное имя провайдера знать не нужно — достаточно env-переменных:

  LLM_PROVIDER=custom
  LLM_BASE_URL=https://api.provider.com/v1   # база API (или .../chat/completions)
  LLM_API_KEY=sk-...                         # ключ (для локальных можно пусто)
  LLM_MODEL=имя-модели

Structured output здесь не гарантирован бэкендом, поэтому: просим строгий JSON
в промпте, пробуем response_format=json_object (не все его знают — при 4xx
повторяем без него), извлекаем JSON из ответа и нормализуем items под
HYP_SCHEMA. Любая ошибка -> None, конвейер остаётся rule-based.
"""
from __future__ import annotations

import json
import os
import re

import httpx

from ..schema import HYP_SCHEMA, SYSTEM_PROMPT
from .base import LLMProvider


def _extract_json(text: str) -> str:
    """Снимаем ```-ограждения и берём внешний {...} — модели любят обёртки."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text


def _normalize(it: dict) -> dict:
    """Мягкая валидация item'а под HYP_SCHEMA (бэкенд схему не гарантирует)."""
    it.setdefault("base_id", None)
    it.setdefault("mechanism", "")
    it.setdefault("rationale", "")
    for key in ("risks", "roadmap"):
        v = it.get(key)
        if not isinstance(v, list):
            it[key] = [str(v)] if v else []
        else:
            it[key] = [str(x) for x in v]
    for key in ("novelty", "feasibility", "risk"):
        try:
            it[key] = max(1, min(5, int(it.get(key, 3))))
        except (TypeError, ValueError):
            it[key] = 3
    return it


class OpenAICompatProvider(LLMProvider):
    name = "custom"

    def __init__(self):
        self.model = os.environ.get("LLM_MODEL", "")
        self.base_url = (os.environ.get("LLM_BASE_URL") or "").rstrip("/")
        self.api_key = os.environ.get("LLM_API_KEY") or ""

    def _configured(self) -> bool:
        if self.base_url and self.model:
            return True
        print("[LLM custom] не настроен: нужны LLM_BASE_URL и LLM_MODEL "
              "(ключ — LLM_API_KEY, если провайдер его требует)")
        return False

    def _chat(self, system: str, user: str) -> str | None:
        url = (self.base_url if self.base_url.endswith("/chat/completions")
               else f"{self.base_url}/chat/completions")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        try:
            r = httpx.post(url, json=payload, headers=headers, timeout=180.0)
            if r.status_code >= 400:
                # часть бэкендов не знает response_format — повторяем без него
                payload.pop("response_format", None)
                r = httpx.post(url, json=payload, headers=headers, timeout=180.0)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:  # сеть/ключ/квота — не роняем конвейер
            print(f"[LLM custom] пропущено: {type(e).__name__}: {e}")
            return None

    def enhance(self, context: dict) -> list[dict] | None:
        if not self._configured():
            return None
        system = (SYSTEM_PROMPT +
                  " Ответ верни строго одним JSON-объектом без пояснений "
                  "и Markdown, по схеме: " +
                  json.dumps(HYP_SCHEMA, ensure_ascii=False))
        content = self._chat(system, json.dumps(context, ensure_ascii=False))
        if not content:
            return None
        try:
            items = json.loads(_extract_json(content)).get("hypotheses") or []
        except Exception as e:
            print(f"[LLM custom] невалидный JSON от модели: {e}")
            return None
        valid = [_normalize(it) for it in items
                 if isinstance(it, dict) and it.get("title")
                 and it.get("hypothesis") and it.get("category")]
        return valid or None

    def translate(self, texts: list[str], lang: str) -> list[str] | None:
        if not self._configured():
            return None
        lang_name = {"en": "английский", "zh": "китайский"}.get(lang, lang)
        system = (f"Переведи каждый элемент массива на {lang_name} язык. "
                  "Технические термины обогащения руд переводи корректно, "
                  "Markdown-разметку, числа и единицы сохраняй как есть. "
                  "Ответ — строго один JSON-объект вида "
                  '{"translations": ["..."]} с массивом той же длины.')
        content = self._chat(system, json.dumps(texts, ensure_ascii=False))
        if not content:
            return None
        try:
            out = json.loads(_extract_json(content))["translations"]
        except Exception as e:
            print(f"[LLM custom translate] невалидный JSON: {e}")
            return None
        return [str(t) for t in out] if len(out) == len(texts) else None
