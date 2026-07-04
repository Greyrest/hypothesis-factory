"""Mock-провайдер: детерминированный ответ без сети (тесты и демо оффлайн)."""
from __future__ import annotations

from .base import LLMProvider


class MockProvider(LLMProvider):
    name = "mock"
    model = "mock-1"

    def translate(self, texts: list[str], lang: str) -> list[str] | None:
        return [f"[{lang}] {t}" for t in texts]

    def enhance(self, context: dict) -> list[dict] | None:
        drafts = context.get("черновики_гипотез", [])
        if not drafts:
            return None
        top = drafts[0]
        return [{
            "base_id": top["id"],
            "title": top["title"],
            "hypothesis": f"Если внедрить «{top['title'].lower()}», то потери "
                          "снизятся (уточнено mock-моделью).",
            "mechanism": "Устранение выявленного узкого места (mock).",
            "category": top.get("category", "CLASSIFY"),
            "risks": ["mock: требуется проверка"],
            "roadmap": ["Лабораторные тесты", "ОПИ на одной секции"],
            "novelty": 2, "feasibility": 4, "risk": 2,
            "rationale": "Детерминированный ответ mock-провайдера для тестов.",
        }]
