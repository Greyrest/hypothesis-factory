"""hf_contracts — универсальные контракты «Фабрики гипотез».

Только доменно-независимые модели и перечисления (ТЗ §2.2, §7.1, §8.2).
Пакет не импортирует ни один другой модуль системы; доменная предметность
(флотация, материаловедение...) подключается адаптерами hf_domains.
"""
from hf_contracts.enums import (
    HYPOTHESIS_STATUSES,
    RUN_STATUSES,
    HypothesisStatus,
    RunStatus,
    Vote,
)
from hf_contracts.models import (
    Constraint,
    Entity,
    Evidence,
    ExpectedEffect,
    ExperimentPlan,
    Fact,
    FeedbackEntry,
    FeedbackRequest,
    GenerationContext,
    Hypothesis,
    HypothesisDraft,
    InputFile,
    Problem,
    Project,
    ProjectCreate,
    ProjectGoal,
    RankingWeights,
    Relation,
    RerankRequest,
    RunRequest,
    Score,
    SourceRef,
    TraceInfo,
)

__all__ = [
    "HypothesisStatus", "HYPOTHESIS_STATUSES", "RunStatus", "RUN_STATUSES", "Vote",
    "Project", "ProjectCreate", "ProjectGoal", "Constraint", "InputFile",
    "Fact", "Entity", "Relation", "Problem", "SourceRef", "Evidence",
    "Score", "ExpectedEffect", "ExperimentPlan", "TraceInfo",
    "Hypothesis", "HypothesisDraft", "GenerationContext",
    "RankingWeights", "FeedbackEntry", "FeedbackRequest",
    "RunRequest", "RerankRequest",
]
