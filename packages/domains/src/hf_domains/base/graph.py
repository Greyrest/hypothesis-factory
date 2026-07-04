"""Универсальный граф знаний проекта: цель <- проблемы -> гипотезы -> источники.

Доменные адаптеры могут строить более богатый граф (флотация добавляет
потоки, классы крупности, ячейки потерь, правила и практики).
"""
from __future__ import annotations

import networkx as nx

from hf_contracts import GenerationContext, Hypothesis, Project
from hf_kg import CoreEdgeType, CoreNodeType, add_edge, add_node, new_graph

GOAL_NODE_ID = "goal:kpi"


def build_project_graph(project: Project, context: GenerationContext,
                        hypotheses: list[Hypothesis]) -> nx.MultiDiGraph:
    G = new_graph("project", project_id=project.id, domain=project.domain)

    add_node(G, GOAL_NODE_ID, CoreNodeType.PROJECT_GOAL,
             project.goal.target_kpi, value=75, wrap=26)

    constraint_ids: dict[str, str] = {}
    for i, c in enumerate(project.constraints):
        cid = f"constraint:{i}"
        add_node(G, cid, CoreNodeType.CONSTRAINT, c.text, value=35, wrap=30)
        constraint_ids[c.text] = cid

    for p in context.problems:
        pid = f"problem:{p.id}"
        add_node(G, pid, CoreNodeType.PROBLEM, p.title, value=55, wrap=22,
                 payload=p.model_dump())
        add_edge(G, pid, GOAL_NODE_ID, CoreEdgeType.TARGETS)

    for h in hypotheses:
        hid = h.trace.graph_node_id or f"hyp:{h.id}"
        add_node(G, hid, CoreNodeType.HYPOTHESIS, h.title, value=80, wrap=24,
                 payload={"title": h.title, "hypothesis": h.hypothesis,
                          "mechanism": h.mechanism, "priority": h.priority,
                          "status": h.status})
        h.trace.graph_node_id = hid
        add_edge(G, hid, GOAL_NODE_ID, CoreEdgeType.TARGETS)
        for p_id in h.trace.problem_ids:
            pid = f"problem:{p_id}"
            if pid in G:
                add_edge(G, pid, hid, CoreEdgeType.ADDRESSED_BY)
        seen_sources = set()
        for ref in list(h.sources) + [e.ref for e in h.evidence if e.ref]:
            if ref.title in seen_sources:
                continue
            seen_sources.add(ref.title)
            sid = f"source:{ref.title}"
            add_node(G, sid, CoreNodeType.SOURCE, ref.title, value=30, wrap=28)
            add_edge(G, hid, sid, CoreEdgeType.SUPPORTED_BY)
        for e in h.evidence:
            if e.source in seen_sources:
                continue
            seen_sources.add(e.source)
            sid = f"source:{e.source}"
            add_node(G, sid, CoreNodeType.SOURCE, e.source, value=30, wrap=28)
            add_edge(G, hid, sid, CoreEdgeType.SUPPORTED_BY)
        for text in h.constraints_violated:
            cid = constraint_ids.get(text)
            if cid:
                add_edge(G, hid, cid, CoreEdgeType.VIOLATES)

    return G
