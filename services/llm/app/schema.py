"""JSON-схема структурированного ответа LLM и системный промпт.

Схема общая для всех провайдеров: любой бэкенд (Anthropic, локальная модель,
mock) обязан вернуть список items этой формы — генератор дальше работает
одинаково, какая бы нейронка ни стояла за сервисом.
"""

CATEGORIES = ["GRIND", "CLASSIFY", "REGRIND", "FLOT", "REAGENT", "CRUSH",
              "TAILS", "AUTO"]

HYP_SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "base_id": {"type": ["string", "null"],
                                "description": "id rule-based черновика, если это его доработка; null для новой гипотезы"},
                    "title": {"type": "string"},
                    "hypothesis": {"type": "string",
                                   "description": "проверяемая формулировка «Если …, то …» с числами"},
                    "mechanism": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "roadmap": {"type": "array", "items": {"type": "string"}},
                    "novelty": {"type": "integer"},
                    "feasibility": {"type": "integer"},
                    "risk": {"type": "integer"},
                    "rationale": {"type": "string",
                                  "description": "обоснование со ссылками на цифры отчёта"},
                },
                "required": ["base_id", "title", "hypothesis", "mechanism",
                             "category", "risks", "roadmap", "novelty",
                             "feasibility", "risk", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hypotheses"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "Ты — технолог-обогатитель Норникеля. По диагностике потерь металлов "
    "с хвостами флотации доработай черновики гипотез и предложи 1-3 новых "
    "(вне каталога, но реалистичных для медно-никелевой флотации). "
    "Формулировка гипотезы — проверяемая, вида «Если <действие>, то "
    "<метрика> изменится на <оценка>», с конкретными тоннами и классами "
    "крупности из диагностики. rationale — 2-4 предложения со ссылками на "
    "цифры. Оценки novelty/feasibility/risk — целые 1-5. Отвечай по-русски."
)


def build_context(diagnosis: dict, drafts: list[dict], catalog: list[dict],
                  rules: list[dict]) -> dict:
    """Компактный контекст для модели из диагностики, черновиков и базы знаний."""
    return {
        "диагностика": {
            "фабрика": diagnosis["plant"],
            "сводка": diagnosis["summary"],
            "находки": [{k: f[k] for k in
                         ("signal", "element_ru", "stream", "title", "tons",
                          "share_of_losses_pct", "detail")}
                        for f in diagnosis["findings"][:14]],
        },
        "черновики_гипотез": [{
            "id": h["id"], "title": h["title"], "category": h["categories"][0],
            "addressable_t": h["expected_effect"]["addressable_t"],
            "evidence": [e["fact"] for e in h["evidence"][:2]],
        } for h in drafts[:12]],
        "каталог_практик": [f"{e['title']} [{e['source']}]" for e in catalog],
        "правила": [f"{r['title']}: {r['text']}" for r in rules],
    }
