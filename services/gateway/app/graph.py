"""Граф знаний фабрики: KPI <- гипотезы <- находки <- классы крупности.

Граф строится из результата конвейера, затем применяются правки эксперта
(patch): удалённые узлы/рёбра и добавленные рёбра. Правки хранятся отдельно
и переживают повторную генерацию.
"""
from __future__ import annotations

EMPTY_PATCH = {"removed_nodes": [], "removed_edges": [], "added_edges": []}


def _edge_id(frm: str, to: str) -> str:
    return f"{frm}->{to}"


def build_graph(result: dict, patch: dict | None = None) -> dict:
    patch = {**EMPTY_PATCH, **(patch or {})}
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    def add_node(nid: str, label: str, group: str):
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "label": label, "group": group})

    def add_edge(frm: str, to: str, arrows: str = ""):
        edges.append({"id": _edge_id(frm, to), "from": frm, "to": to,
                      "arrows": arrows})

    kpi_label = (result.get("project") or {}).get("target_kpi") \
        or "KPI: снижение потерь Ni/Cu с хвостами"
    add_node("kpi", kpi_label, "kpi")

    for f in result["findings"]:
        if f.get("informational"):
            continue
        add_node("f:" + f["id"], f["title"][:48], "finding")
        for cls in f.get("classes", []):
            add_node("c:" + cls, cls + " мкм", "class")
            add_edge("c:" + cls, "f:" + f["id"])

    for h in result["hypotheses"]:
        add_node("h:" + h["id"], f"{h.get('rank', '?')}. {h['title'][:48]}", "hyp")
        add_edge("h:" + h["id"], "kpi", "to")
        for fid in h.get("finding_ids", []):
            if "f:" + fid in seen:
                add_edge("f:" + fid, "h:" + h["id"], "to")

    # правки эксперта
    removed_n = set(patch["removed_nodes"])
    removed_e = set(patch["removed_edges"])
    nodes = [n for n in nodes if n["id"] not in removed_n]
    alive = {n["id"] for n in nodes}
    edges = [e for e in edges
             if e["id"] not in removed_e
             and e["from"] in alive and e["to"] in alive]
    have = {e["id"] for e in edges}
    for e in patch["added_edges"]:
        eid = _edge_id(e["from"], e["to"])
        if eid not in have and e["from"] in alive and e["to"] in alive:
            edges.append({"id": eid, "from": e["from"], "to": e["to"],
                          "arrows": "to", "expert": True})

    return {"nodes": nodes, "edges": edges, "patch": patch}


def merge_patch(patch: dict | None, delta: dict) -> dict:
    """Слить новые правки с накопленными (идемпотентно)."""
    patch = {**EMPTY_PATCH, **(patch or {})}
    out = {
        "removed_nodes": sorted(set(patch["removed_nodes"])
                                | set(delta.get("removed_nodes", []))),
        "removed_edges": sorted(set(patch["removed_edges"])
                                | set(delta.get("removed_edges", []))),
        "added_edges": list(patch["added_edges"]),
    }
    have = {_edge_id(e["from"], e["to"]) for e in out["added_edges"]}
    for e in delta.get("added_edges", []):
        if _edge_id(e["from"], e["to"]) not in have:
            out["added_edges"].append({"from": e["from"], "to": e["to"]})
    # добавление ребра снимает его прежнее удаление
    added_ids = {_edge_id(e["from"], e["to"]) for e in out["added_edges"]}
    out["removed_edges"] = [i for i in out["removed_edges"] if i not in added_ids]
    return out
