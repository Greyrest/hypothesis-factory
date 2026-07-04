"""Запросы к графу знаний. Все функции возвращают готовый vis-формат:
{"nodes": [{id, label, group, value, payload?}], "edges": [{from, to, arrows?}]}.
"""
from __future__ import annotations

from enum import Enum

import networkx as nx

from hf_kg.serializers import to_vis_nodes


def _names(edge_types) -> set[str] | None:
    if edge_types is None:
        return None
    return {e.value if isinstance(e, Enum) else str(e) for e in edge_types}


def _dedup_edges(pairs) -> list[dict]:
    seen, out = set(), []
    for u, v in pairs:
        if (u, v) not in seen:
            seen.add((u, v))
            out.append({"from": u, "to": v, "arrows": "to"})
    return out


def full_view(G: nx.MultiDiGraph) -> dict:
    """Полный вид: все узлы и рёбра графа."""
    return {
        "nodes": to_vis_nodes(G, G.nodes),
        "edges": _dedup_edges((u, v) for u, v, _k in G.edges(keys=True)),
    }


def neighbors_view(G: nx.MultiDiGraph, node_id: str, depth: int = 1) -> dict:
    """Окрестность узла на заданную глубину (в обе стороны)."""
    if node_id not in G:
        raise KeyError(node_id)
    keep = {node_id}
    frontier = {node_id}
    for _ in range(depth):
        nxt = set()
        for n in frontier:
            nxt.update(G.successors(n))
            nxt.update(G.predecessors(n))
        frontier = nxt - keep
        keep |= nxt
    sub = G.subgraph(keep)
    return {
        "nodes": to_vis_nodes(G, keep),
        "edges": _dedup_edges((u, v) for u, v, _k in sub.edges(keys=True)),
    }


def trace_view(G: nx.MultiDiGraph, start: str,
               up_edges=None, down_edges=None) -> dict:
    """Трассировка обоснования (ТЗ §9.4).

    От узла `start` транзитивно поднимаемся по ВХОДЯЩИМ рёбрам типов
    `up_edges` (цепочка «гипотеза <- проблема <- факт <- данные»), затем от
    каждого достигнутого узла делаем один шаг по ИСХОДЯЩИМ рёбрам типов
    `down_edges` (источники, правила, категории, механизмы...).
    Наборы типов задаёт вызывающий (доменный адаптер или ядро).
    """
    if start not in G:
        raise KeyError(start)
    up = _names(up_edges) or set()
    down = _names(down_edges) or set()

    keep: set[str] = {start}
    pairs: list[tuple[str, str]] = []

    frontier = [start]
    while frontier:
        nxt = []
        for node in frontier:
            for u, _v, k in G.in_edges(node, keys=True):
                if k in up:
                    pairs.append((u, node))
                    if u not in keep:
                        keep.add(u)
                        nxt.append(u)
        frontier = nxt

    for node in list(keep):
        for _u, v, k in G.out_edges(node, keys=True):
            if k in down:
                pairs.append((node, v))
                keep.add(v)

    return {"nodes": to_vis_nodes(G, keep), "edges": _dedup_edges(pairs)}
