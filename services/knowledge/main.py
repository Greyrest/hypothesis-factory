from __future__ import annotations

from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Query

from services.common.health import health
from services.common.models import GraphRequest, KnowledgeRequest

app = FastAPI(
    title="Hypothesis Factory · Knowledge Service",
    version="2.0.0",
    description="Builds retrieval context, evidence graphs, and hypothesis traces.",
)


DEFAULT_PRACTICES = [
    ("grind-01", "Оптимизация шаровой загрузки и режима измельчения", ["coarse_locked"], "GRIND", "мельница"),
    ("classify-01", "Настройка гидроциклонов и классифицирующих аппаратов", ["coarse_share", "coarse_locked"], "CLASSIFY", "гидроциклон"),
    ("regrind-01", "Доизмельчение сростков в отдельном цикле", ["mid_locked", "coarse_locked"], "REGRIND", "мельница доизмельчения"),
    ("flot-01", "Увеличение эффективного времени флотации", ["mid_liberated"], "FLOT", "флотомашины"),
    ("reagent-01", "Оптимизация реагентного режима тонких классов", ["fine_liberated", "mid_liberated"], "REAGENT", "дозаторы реагентов"),
    ("tails-01", "Классификация хвостов с возвратом песковой фракции", ["coarse_share", "tails_recycle"], "TAILS", "классификатор хвостов"),
    ("magnetic-01", "Магнитная сепарация пирротинового потока", ["pyrrhotite"], "REGRIND", "магнитный сепаратор"),
    ("auto-01", "Автоматическое управление плотностью и гранулометрией", ["coarse_share", "mid_liberated"], "AUTO", "датчики и АСУТП"),
]


def _catalog() -> list[dict]:
    return [
        {
            "id": item_id,
            "title": title,
            "source": "Встроенный каталог проверяемых технологических практик",
            "plants": [],
            "signals": signals,
            "categories": [category],
            "equipment": equipment,
            "feasibility": 4 if category in {"CLASSIFY", "FLOT", "AUTO"} else 3,
            "novelty": 2 if category in {"GRIND", "CLASSIFY"} else 3,
            "risk": 2 if category in {"CLASSIFY", "AUTO"} else 3,
            "capex": "высокий" if category in {"REGRIND", "TAILS"} else "средний",
        }
        for item_id, title, signals, category, equipment in DEFAULT_PRACTICES
    ]


@app.get("/api/v1/health", tags=["System"])
def service_health() -> dict:
    return health("knowledge")


@app.post("/api/v1/context", tags=["Knowledge"], summary="Build retrieval context")
def build_context(request: KnowledgeRequest) -> dict:
    facts = request.ingestion.get("facts", [])
    chunks = [
        {
            "id": fact.get("id", f"fact-{index}"),
            "kind": "source",
            "source": fact.get("filename", "uploaded source"),
            "text": fact.get("text") or str(fact.get("data", ""))[:4000],
        }
        for index, fact in enumerate(facts)
        if fact.get("text") or fact.get("data")
    ]
    rules: list[dict] = []
    if request.domain == "mining_flotation":
        from knowledge_base import DOMAIN_RULES

        rules = DOMAIN_RULES
        chunks.extend({
            "id": rule["id"],
            "kind": "rule",
            "source": rule["source"],
            "text": f"{rule['title']}. {rule['text']}",
        } for rule in rules)
    return {
        "project_id": request.project_id,
        "chunks": chunks,
        "catalog": _catalog() if request.domain == "mining_flotation" else [],
        "rules": rules,
        "stats": {"chunks": len(chunks), "catalog": len(_catalog()) if request.domain == "mining_flotation" else 0},
    }


def _add_node(nodes: dict, node_id: str, label: str, group: str, payload=None) -> None:
    nodes.setdefault(node_id, {"id": node_id, "label": label, "group": group, "payload": payload or {}})


@app.post("/api/v1/graphs", tags=["Graph"], summary="Build project knowledge graph")
def build_graph(request: GraphRequest) -> dict:
    project = request.project
    diagnosis = request.ingestion.get("diagnosis", {})
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    goal_id = f"goal:{project['id']}"
    _add_node(nodes, goal_id, project.get("target_kpi", "KPI"), "goal")

    for finding in diagnosis.get("findings", []):
        finding_id = f"finding:{finding['id']}"
        _add_node(nodes, finding_id, finding.get("title", finding["id"]), "problem", finding)
        edges.append({"from": finding_id, "to": goal_id, "type": "affects"})

    for hypothesis in request.hypotheses:
        hypothesis_id = f"hypothesis:{hypothesis['id']}"
        _add_node(nodes, hypothesis_id, hypothesis["title"], "hypothesis", {
            "rank": hypothesis.get("rank"),
            "priority": hypothesis.get("scores", {}).get("priority"),
        })
        edges.append({"from": hypothesis_id, "to": goal_id, "type": "targets"})
        for finding_id in hypothesis.get("finding_ids", []):
            source = f"finding:{finding_id}"
            if source in nodes:
                edges.append({"from": source, "to": hypothesis_id, "type": "addressed_by"})
        for index, evidence in enumerate(hypothesis.get("evidence", [])):
            evidence_id = f"evidence:{hypothesis['id']}:{index}"
            _add_node(nodes, evidence_id, evidence.get("source", "Источник"), "evidence", evidence)
            edges.append({"from": evidence_id, "to": hypothesis_id, "type": "supports"})

    return {"nodes": list(nodes.values()), "edges": edges, "meta": {"project_id": project["id"]}}


@app.post("/api/v1/traces/{hypothesis_id}", tags=["Graph"], summary="Extract hypothesis trace")
def trace(hypothesis_id: str, graph: dict, depth: int = Query(2, ge=1, le=5)) -> dict:
    start = f"hypothesis:{hypothesis_id}"
    nodes_by_id = {node["id"]: node for node in graph.get("nodes", [])}
    if start not in nodes_by_id:
        raise HTTPException(status_code=404, detail="hypothesis is not present in graph")
    adjacent: dict[str, list[str]] = defaultdict(list)
    for edge in graph.get("edges", []):
        adjacent[edge["from"]].append(edge["to"])
        adjacent[edge["to"]].append(edge["from"])
    keep = {start}
    queue = deque([(start, 0)])
    while queue:
        node, level = queue.popleft()
        if level >= depth:
            continue
        for neighbor in adjacent[node]:
            if neighbor not in keep:
                keep.add(neighbor)
                queue.append((neighbor, level + 1))
    return {
        "nodes": [nodes_by_id[node_id] for node_id in keep],
        "edges": [edge for edge in graph.get("edges", []) if edge["from"] in keep and edge["to"] in keep],
    }

