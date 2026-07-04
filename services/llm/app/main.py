"""LLM-сервис: единственная точка работы с нейронкой.

POST /api/v1/enhance — полировка черновиков и генерация новых гипотез
структурированным выводом. Провайдер и модель выбираются env-переменными
LLM_PROVIDER / LLM_MODEL: сменить нейронку = перезапустить один этот сервис.
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .providers import get_provider
from .schema import build_context

app = FastAPI(
    title="HF LLM Service",
    description="Абстракция над LLM-провайдерами (anthropic | mock | none). "
    "Возвращает structured-ответ единой схемы независимо от модели; "
    "при недоступности LLM отвечает items=null и конвейер живёт rule-based.",
    version="1.0.0",
)

_provider = get_provider()


class EnhanceRequest(BaseModel):
    diagnosis: dict
    drafts: list[dict]
    catalog: list[dict] = []
    rules: list[dict] = []


class EnhanceResponse(BaseModel):
    items: list[dict] | None
    provider: str
    model: str


class TranslateRequest(BaseModel):
    texts: list[str]
    lang: str  # en | zh


class TranslateResponse(BaseModel):
    translations: list[str] | None
    provider: str


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "service": "llm",
            "provider": _provider.name, "model": _provider.model}


@app.post("/api/v1/enhance", response_model=EnhanceResponse)
def enhance(req: EnhanceRequest) -> EnhanceResponse:
    ctx = build_context(req.diagnosis, req.drafts, req.catalog, req.rules)
    items = _provider.enhance(ctx)
    return EnhanceResponse(items=items, provider=_provider.name,
                           model=_provider.model)


@app.post("/api/v1/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest) -> TranslateResponse:
    """Мультиязычность (RU/EN/CN из ТЗ): перевод отчётов через LLM-слой."""
    return TranslateResponse(
        translations=_provider.translate(req.texts, req.lang),
        provider=_provider.name)
