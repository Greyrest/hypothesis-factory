"""Хранение графа: node-link JSON на диске.

Формат сериализации собственный (стабильный между версиями networkx):
{"meta": {...}, "nodes": [{"id", ...attrs}], "edges": [{"from", "to", "type"}]}.
Интерфейс функций — задел под альтернативные хранилища (Neo4j, ТЗ K-6).
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx


def graph_to_dict(G: nx.MultiDiGraph) -> dict:
    return {
        "meta": dict(G.graph),
        "nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
        "edges": [{"from": u, "to": v, "type": k}
                  for u, v, k in G.edges(keys=True)],
    }


def graph_from_dict(data: dict) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph(**data.get("meta", {}))
    for node in data["nodes"]:
        attrs = dict(node)
        nid = attrs.pop("id")
        G.add_node(nid, **attrs)
    for edge in data["edges"]:
        G.add_edge(edge["from"], edge["to"], key=edge["type"])
    return G


def save_graph(G: nx.MultiDiGraph, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph_to_dict(G), ensure_ascii=False),
                    encoding="utf-8")
    return path


def load_graph(path: str | Path) -> nx.MultiDiGraph:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return graph_from_dict(data)
