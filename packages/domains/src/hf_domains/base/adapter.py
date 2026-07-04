"""Интерфейс доменного адаптера (ТЗ §6.2) и база с поведением по умолчанию."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import networkx as nx

from hf_contracts import (
    Constraint,
    Entity,
    ExpectedEffect,
    ExperimentPlan,
    Fact,
    GenerationContext,
    Hypothesis,
    InputFile,
    Problem,
    Project,
    ProjectGoal,
    RankingWeights,
)
from hf_llm import LLMConfig

from hf_domains.base.graph import build_project_graph
from hf_domains.base.ranking import core_rank


@runtime_checkable
class DomainAdapter(Protocol):
    domain_id: str
    title: str
    supported_formats: tuple[str, ...]

    def parse_inputs(self, files: list[InputFile]) -> list[Fact]: ...

    def extract_entities(self, facts: list[Fact]) -> list[Entity]: ...

    def diagnose(self, goal: ProjectGoal, facts: list[Fact],
                 constraints: list[Constraint]) -> list[Problem]: ...

    def load_knowledge(self, files: list[InputFile]) -> list[dict]:
        """Чанки базы знаний домена: {'id','kind','source','text'}."""
        ...

    def build_generation_context(self, goal: ProjectGoal,
                                 problems: list[Problem], facts: list[Fact],
                                 knowledge: list) -> GenerationContext: ...

    def generate_rule_based(self, context: GenerationContext) -> list[Hypothesis]: ...

    def estimate_effect(self, hypothesis: Hypothesis,
                        facts: list[Fact]) -> ExpectedEffect: ...

    def validation_plan(self, hypothesis: Hypothesis) -> ExperimentPlan: ...

    # --- расширения ядра (у Base есть реализации по умолчанию) ---
    def llm_enhance(self, context: GenerationContext, drafts: list[Hypothesis],
                    config: LLMConfig) -> list[Hypothesis] | None: ...

    def rank_hypotheses(self, hypotheses: list[Hypothesis],
                        weights: RankingWeights,
                        votes: dict[str, str] | None = None) -> None: ...

    def build_graph(self, project: Project, context: GenerationContext,
                    hypotheses: list[Hypothesis]) -> nx.MultiDiGraph: ...

    def graph_view(self, G: nx.MultiDiGraph, view: str) -> dict: ...

    def trace_edges(self) -> tuple[list[str], list[str]]: ...

    def default_weights(self) -> RankingWeights: ...


class BaseDomainAdapter:
    """База адаптера: универсальные реализации необязательных методов."""

    domain_id = "base"
    title = "Базовый адаптер"
    supported_formats = (".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".json")

    def __init__(self):
        self._constraints: list[Constraint] = []

    # обязательные методы parse_inputs / diagnose / generate_rule_based /
    # build_generation_context реализует конкретный домен

    def extract_entities(self, facts: list[Fact]) -> list[Entity]:
        return []

    def load_knowledge(self, files: list[InputFile]) -> list[dict]:
        return []

    def estimate_effect(self, hypothesis: Hypothesis,
                        facts: list[Fact]) -> ExpectedEffect:
        return hypothesis.expected_effect

    def validation_plan(self, hypothesis: Hypothesis) -> ExperimentPlan:
        return hypothesis.validation_plan

    def llm_enhance(self, context: GenerationContext, drafts: list[Hypothesis],
                    config: LLMConfig) -> list[Hypothesis] | None:
        return None

    def rank_hypotheses(self, hypotheses: list[Hypothesis],
                        weights: RankingWeights,
                        votes: dict[str, str] | None = None) -> None:
        core_rank(hypotheses, weights, votes)

    def build_graph(self, project: Project, context: GenerationContext,
                    hypotheses: list[Hypothesis]) -> nx.MultiDiGraph:
        return build_project_graph(project, context, hypotheses)

    def graph_view(self, G: nx.MultiDiGraph, view: str) -> dict:
        from hf_kg import full_view

        return full_view(G)

    def trace_edges(self) -> tuple[list[str], list[str]]:
        return (
            ["addressed_by"],
            ["supported_by", "targets", "violates", "requires",
             "tested_in", "derived_from"],
        )

    def default_weights(self) -> RankingWeights:
        return RankingWeights()
