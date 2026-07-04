"""Универсальные модели «Фабрики гипотез» (ТЗ §2.2, §7.1, §8.2).

Главная сущность системы — гипотеза: «Если изменить фактор X в условиях Y,
то целевой KPI Z изменится на величину Δ, потому что сработает механизм M».
Доменные детали (потоки, классы крупности, сплавы, режимы) живут в payload'ах
(`data`, `domain_data`) и в доменных адаптерах, а не в ядре.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hf_contracts.enums import HypothesisStatus, Vote


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- проект / вход
class ProjectGoal(BaseModel):
    """Целевой KPI или технологическая проблема R&D-задачи."""
    target_kpi: str
    description: str | None = None
    direction: Literal["increase", "decrease"] | None = None
    baseline: str | None = None


class Constraint(BaseModel):
    """Ограничение проекта: сырьё, бюджет, оборудование, нормативы, сроки."""
    text: str
    kind: str | None = None


class InputFile(BaseModel):
    """Загруженный документ или таблица (PDF/DOCX/TXT/CSV/XLSX/JSON)."""
    id: str
    filename: str
    path: str
    kind: str | None = None       # подсказка адаптеру: report / knowledge / data ...
    media_type: str | None = None


class Project(BaseModel):
    """R&D-задача: домен, KPI, ограничения, файлы."""
    id: str
    domain: str
    title: str | None = None
    goal: ProjectGoal
    constraints: list[Constraint] = Field(default_factory=list)
    files: list[InputFile] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    status: Literal["new", "running", "done", "error"] = "new"
    engine: str | None = None     # чем сгенерирован последний результат
    updated_at: str = Field(default_factory=_now)


# ------------------------------------------------------------- факты и знания
class Fact(BaseModel):
    """Извлечённый факт: единица нормализованных данных из файла/таблицы."""
    id: str
    kind: str                     # text | experiment | parsed_report | data ...
    text: str | None = None
    data: dict = Field(default_factory=dict)
    source_id: str | None = None  # id InputFile или SourceRef


class Entity(BaseModel):
    """Сущность домена: материал, процесс, параметр, свойство, поток..."""
    id: str
    type: str
    name: str
    attrs: dict = Field(default_factory=dict)


class Relation(BaseModel):
    """Связь между сущностями: влияет на / улучшает / требует / ограничивает."""
    id: str
    type: str
    source: str
    target: str
    attrs: dict = Field(default_factory=dict)


class Problem(BaseModel):
    """Найденная проблема, разрыв или зона улучшения (вход генерации гипотез)."""
    id: str
    title: str
    description: str = ""
    kind: str | None = None       # доменный сигнал (напр. coarse_locked)
    severity: float | None = None # 0..1 — доля/важность, если оценима
    data: dict = Field(default_factory=dict)


class SourceRef(BaseModel):
    """Ссылка на источник: статья, патент, отчёт, учебник, правило."""
    title: str
    kind: str | None = None       # article | patent | report | rule | guide ...
    locator: str | None = None    # страница/раздел/ячейка


class Evidence(BaseModel):
    """Основание гипотезы: факт + источник (данные, аналогия, правило)."""
    source: str
    fact: str
    kind: str | None = None
    ref: SourceRef | None = None


# ----------------------------------------------------------- оценки и эффекты
class Score(BaseModel):
    """Нормированная оценка критерия: value в 0..1, raw — доменная шкала."""
    value: float = Field(ge=0.0, le=1.0)
    raw: float | None = None
    scale: str | None = None      # например "1-5" или "т/период"
    rationale: str | None = None


class ExpectedEffect(BaseModel):
    """Ожидаемый эффект на целевой KPI (диапазон + явное допущение)."""
    kpi: str
    estimate: str                 # человекочитаемо: «10–15 %», «−460…−919 т»
    low: float | None = None
    high: float | None = None
    unit: str | None = None
    assumption: str | None = None
    data: dict = Field(default_factory=dict)   # доменные детали (addressable_t...)


class ExperimentPlan(BaseModel):
    """План проверки гипотезы (дорожная карта)."""
    steps: list[str] = Field(default_factory=list)
    duration: str | None = None
    resources: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    failure_criteria: list[str] = Field(default_factory=list)


class TraceInfo(BaseModel):
    """Привязка гипотезы к проблемам/фактам/источникам и узлу графа знаний."""
    problem_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    graph_node_id: str | None = None


# ------------------------------------------------------------------- гипотеза
class Hypothesis(BaseModel):
    """Универсальная карточка гипотезы (ТЗ §7.1)."""
    id: str
    rank: int | None = None

    title: str
    hypothesis: str
    domain: str
    target_kpi: str

    problem: str = ""
    mechanism: str = ""
    expected_effect: ExpectedEffect

    evidence: list[Evidence] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)

    novelty: Score
    feasibility: Score
    risk: Score
    impact: Score
    cost: Score | None = None
    uncertainty: Score | None = None
    evidence_strength: Score | None = None
    strategic_value: Score | None = None

    constraints_matched: list[str] = Field(default_factory=list)
    constraints_violated: list[str] = Field(default_factory=list)

    risks: list[str] = Field(default_factory=list)
    validation_plan: ExperimentPlan = Field(default_factory=ExperimentPlan)

    status: HypothesisStatus = "rule_based"
    priority: float | None = None
    feedback_adj: float = 0.0

    trace: TraceInfo = Field(default_factory=TraceInfo)
    domain_data: dict = Field(default_factory=dict)  # legacy-карточка адаптера


HypothesisDraft = Hypothesis  # черновик = частично заполненная карточка


class GenerationContext(BaseModel):
    """Контекст генерации, который адаптер собирает для rule-based/LLM-шагов."""
    goal: ProjectGoal
    constraints: list[Constraint] = Field(default_factory=list)
    problems: list[Problem] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    knowledge: list[Evidence] = Field(default_factory=list)
    domain_context: dict = Field(default_factory=dict)


# ----------------------------------------------------------------- ранжирование
class RankingWeights(BaseModel):
    """Гибкие веса критериев (ТЗ §8.2); положительные — в плюс, risk/cost/
    uncertainty вычитаются (§8.3)."""
    impact: float = 0.30
    novelty: float = 0.20
    feasibility: float = 0.20
    risk: float = 0.15
    cost: float = 0.10
    evidence_strength: float = 0.05
    uncertainty: float = 0.0
    strategic_value: float = 0.0


class FeedbackEntry(BaseModel):
    """Экспертная оценка гипотезы."""
    hypothesis_id: str
    vote: Vote | None = None
    comment: str | None = None
    expert_id: str = "local"
    updated_at: str = Field(default_factory=_now)


# ------------------------------------------------------------------ API-модели
class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    target_kpi: str
    title: str | None = None
    description: str | None = None
    constraints: list[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_llm: bool | None = None            # None => из настроек сервера
    weights: RankingWeights | None = None  # None => веса домена по умолчанию


class RerankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: RankingWeights | None = None


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vote: Vote | None
    comment: str | None = None

    @model_validator(mode="after")
    def _non_empty(self) -> "FeedbackRequest":
        return self
