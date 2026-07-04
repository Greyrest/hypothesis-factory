"""Pydantic-модели карточки гипотезы и результата по фабрике.

Модели описывают фактические JSON-формы конвейера (парсер -> диагностика ->
генерация). extra="allow" — сервисы могут добавлять поля, не ломая соседей.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class Component(_Open):
    """Компонент потерь (элемент/минерал), извлечённый ingestion из отчёта.

    Конвейер не знает конкретных металлов: везде дальше используются id
    компонентов и словари, ключованные этими id."""
    id: str
    label: str
    unit: str = "т"
    recoverable_forms: list[str] = []


class Evidence(_Open):
    source: str
    fact: str


class ExpectedEffect(_Open):
    addressable_t: dict[str, float]
    uplift_pct: list[float]
    kpi_delta_t: dict[str, list[float]]
    kpi: str
    assumption: str


class Scores(_Open):
    feasibility: int
    novelty: int
    risk: int
    impact_t: float
    priority: float | None = None
    feedback_adj: float | None = None
    diversity_adj: float | None = None


class Hypothesis(_Open):
    id: str
    rank: int | None = None
    title: str
    hypothesis: str
    categories: list[str]
    category_ru: str
    equipment: str = ""
    streams: list[str] = []
    mechanism: str
    evidence: list[Evidence]
    expected_effect: ExpectedEffect
    scores: Scores
    risks: list[str]
    roadmap: list[str]
    status: str
    sources: list[str]
    matched_signals: list[str] = []
    finding_ids: list[str] = []


class Finding(_Open):
    id: str
    signal: str
    element: str
    element_ru: str
    stream: str
    title: str
    tons: float
    share_of_losses_pct: float
    classes: list[str] = []
    forms: list[str] = []
    detail: str
    informational: bool | None = None


class Summary(_Open):
    """Сводка потерь: словари по id компонента. Плоские алиасы вида
    losses_<id>_t добавляются диагностикой для обратной совместимости
    (их читает фронтенд) и проходят через extra="allow"."""
    losses_t: dict[str, float] = {}
    recoverable_t: dict[str, float] = {}
    recoverable_pct: dict[str, float] = {}


class PlantResult(_Open):
    plant: str
    engine: str
    components: list[Component] = []
    summary: Summary
    hypotheses: list[Hypothesis]
    findings: list[Finding]
    cells: list[dict] = []
