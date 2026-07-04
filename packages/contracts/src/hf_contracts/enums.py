"""Универсальные перечисления ядра (ТЗ §7.1).

Доменные перечисления (сигналы флотации, категории мероприятий и т.п.)
живут в соответствующих адаптерах hf_domains, а не здесь.
"""
from __future__ import annotations

from typing import Literal

HypothesisStatus = Literal[
    "rule_based",        # порождена правилами/шаблонами домена
    "rag_llm",           # сгенерирована/доработана LLM с опорой на контекст
    "predictive_model",  # предсказана моделью (задел)
    "expert_added",      # добавлена экспертом
    "confirmed",         # подтверждена проверкой
    "rejected",          # отклонена
]
HYPOTHESIS_STATUSES: tuple[str, ...] = (
    "rule_based", "rag_llm", "predictive_model",
    "expert_added", "confirmed", "rejected",
)

Vote = Literal["up", "down"]

RunStatus = Literal["queued", "running", "done", "error"]
RUN_STATUSES: tuple[str, ...] = ("queued", "running", "done", "error")
