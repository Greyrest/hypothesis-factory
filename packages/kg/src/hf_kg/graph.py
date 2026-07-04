"""Создание графа знаний: тонкие валидирующие обёртки над networkx.

Каждый узел обязан иметь `type` и `label`; тип ребра служит ключом
мультиграфа, поэтому повторное добавление того же ребра не создаёт дубликат.
Опциональные атрибуты узла, которые понимает сериализатор vis:
`value` (размер), `payload` (детали для панели на дашборде), `wrap` (ширина
переноса подписи).
"""
from __future__ import annotations

from enum import Enum

import networkx as nx


def _s(v) -> str:
    return v.value if isinstance(v, Enum) else str(v)


def new_graph(kind: str, **meta) -> nx.MultiDiGraph:
    return nx.MultiDiGraph(kind=kind, **meta)


def add_node(G: nx.MultiDiGraph, node_id: str, node_type, label: str, **attrs):
    """Добавляет узел; повторное добавление не затирает существующий."""
    if not node_id:
        raise ValueError("пустой id узла графа знаний")
    if node_id not in G:
        G.add_node(node_id, type=_s(node_type), label=str(label), **attrs)
    return node_id


def add_edge(G: nx.MultiDiGraph, u: str, v: str, edge_type):
    if u not in G or v not in G:
        raise KeyError(f"ребро {u} -> {v}: узел не существует")
    G.add_edge(u, v, key=_s(edge_type))
