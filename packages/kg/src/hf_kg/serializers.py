"""Сериализация узлов графа в формат vis-network.

Узел графа сам несёт подсказки отображения (label, value, wrap, payload) —
их выставляет построитель (ядро или доменный адаптер) при создании узла.
"""
from __future__ import annotations

import networkx as nx


def wrap(text: str, width: int) -> str:
    """Перенос подписи по словам (порт JS-функции прототипа)."""
    words = str(text).split(" ")
    line, out = "", []
    for wd in words:
        if len(line + wd) > width:
            out.append(line)
            line = ""
        line += wd + " "
    out.append(line)
    return "\n".join(out).strip()


def vis_node(G: nx.MultiDiGraph, node_id: str) -> dict:
    d = G.nodes[node_id]
    node: dict = {
        "id": node_id,
        "group": d.get("type", ""),
        "label": wrap(d.get("label", node_id), int(d.get("wrap", 24))),
        "value": d.get("value", 50),
    }
    if d.get("payload") is not None:
        node["payload"] = d["payload"]
    return node


def to_vis_nodes(G: nx.MultiDiGraph, node_ids) -> list[dict]:
    return [vis_node(G, nid) for nid in node_ids]
