"""Универсальное ранжирование гипотез с гибкими весами (ТЗ §8.3).

priority = 100 * (w_impact*impact + w_novelty*novelty + w_feasibility*feasibility
                  + w_evidence*evidence_strength + w_strategic*strategic_value
                  - w_risk*risk - w_cost*cost - w_uncertainty*uncertainty)
           + поправка экспертного фидбэка (голос ±5).

Все критерии — нормированные Score.value в 0..1. Домены могут заменять
формулу своей (mining_flotation сохраняет формулу прототипа).
"""
from __future__ import annotations

from hf_contracts import Hypothesis, RankingWeights, Score

FEEDBACK_VOTE_ADJ = 5.0


def _v(score: Score | None) -> float:
    return score.value if score is not None else 0.0


def core_rank(hypotheses: list[Hypothesis], weights: RankingWeights,
              votes: dict[str, str] | None = None) -> None:
    w = weights
    votes = votes or {}
    for h in hypotheses:
        p = (w.impact * _v(h.impact)
             + w.novelty * _v(h.novelty)
             + w.feasibility * _v(h.feasibility)
             + w.evidence_strength * _v(h.evidence_strength)
             + w.strategic_value * _v(h.strategic_value)
             - w.risk * _v(h.risk)
             - w.cost * _v(h.cost)
             - w.uncertainty * _v(h.uncertainty))
        vote = votes.get(h.id)
        adj = FEEDBACK_VOTE_ADJ if vote == "up" else (
            -FEEDBACK_VOTE_ADJ if vote == "down" else 0.0)
        h.feedback_adj = adj
        h.priority = round(100 * p + adj, 1)
    hypotheses.sort(key=lambda h: -(h.priority or 0.0))
    for i, h in enumerate(hypotheses, 1):
        h.rank = i
