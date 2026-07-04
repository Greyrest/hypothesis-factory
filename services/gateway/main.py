from __future__ import annotations

import csv
import io
import json
import re
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from services.common.config import (
    DATA_DIR,
    DB_PATH,
    HYPOTHESIS_URL,
    INGESTION_URL,
    KNOWLEDGE_URL,
    MODEL_RUNTIME_URL,
    prepare_runtime,
)
from services.common.health import health
from services.common.http import get_json, post_json
from services.common.models import (
    FeedbackRequest,
    ModelSelection,
    ProjectCreate,
    RerankRequest,
    RunRequest,
)
from services.gateway.store import Store, now

store = Store(DB_PATH)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    prepare_runtime()
    store.init()
    yield


app = FastAPI(
    title="Hypothesis Factory API",
    version="2.0.0",
    description=(
        "Public API for R&D projects, evidence-backed hypothesis generation, ranking, "
        "knowledge graphs, expert feedback, exports, and model selection."
    ),
    lifespan=lifespan,
    openapi_tags=[
        {"name": "System", "description": "Health, domains, and model capabilities."},
        {"name": "Projects", "description": "R&D project lifecycle and input files."},
        {"name": "Runs", "description": "Asynchronous pipeline orchestration."},
        {"name": "Hypotheses", "description": "Results, details, feedback, and ranking."},
        {"name": "Knowledge", "description": "Evidence graph and trace."},
        {"name": "Export", "description": "Machine-readable and human-readable reports."},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in __import__("os").getenv("HF_CORS_ORIGINS", "http://localhost:3000").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _project(project_id: str) -> dict:
    project = store.get("projects", "id", project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


def _result(project_id: str) -> dict:
    result = store.get("results", "project_id", project_id)
    if not result:
        raise HTTPException(status_code=404, detail="project has no completed generation")
    return result


def _files(project_id: str) -> list[dict]:
    return store.list("files", project_id)


def _feedback(project_id: str) -> dict[str, dict]:
    return {item["hypothesis_id"]: item for item in store.list("feedback", project_id)}


def _present_project(project: dict) -> dict:
    return project | {"files": _files(project["id"]), "latest_run": next(iter(store.list("runs", project["id"])), None)}


@app.get("/api/v1/health", tags=["System"], summary="Gateway health")
def gateway_health() -> dict:
    return health("gateway")


@app.get("/api/v1/domains", tags=["System"], summary="List domain adapters")
def domains() -> dict:
    return {"domains": [
        {"id": "mining_flotation", "title": "Обогащение: потери металлов с хвостами", "formats": [".xlsx", ".pdf", ".docx", ".txt"]},
        {"id": "generic", "title": "Универсальный R&D-контур", "formats": [".pdf", ".docx", ".txt", ".md", ".csv", ".json"]},
    ]}


@app.get("/api/v1/models", tags=["System"], summary="List selectable neural models")
async def models() -> dict:
    return await get_json(MODEL_RUNTIME_URL, "/api/v1/models")


@app.post("/api/v1/projects", tags=["Projects"], status_code=201, summary="Create R&D project")
def create_project(payload: ProjectCreate) -> dict:
    project_id = str(uuid.uuid4())
    timestamp = now()
    project = {
        "id": project_id,
        **payload.model_dump(),
        "status": "new",
        "model": ModelSelection().model_dump(),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    store.put("projects", "id", project_id, project)
    return _present_project(project)


@app.get("/api/v1/projects", tags=["Projects"], summary="List projects")
def list_projects() -> dict:
    return {"items": [_present_project(project) for project in store.list("projects")]}


@app.get("/api/v1/projects/{project_id}", tags=["Projects"], summary="Get project")
def get_project(project_id: str) -> dict:
    return _present_project(_project(project_id))


@app.post("/api/v1/projects/{project_id}/files", tags=["Projects"], status_code=201, summary="Upload source file")
async def upload_file(project_id: str, file: UploadFile = File(...), kind: str = Query("data")) -> dict:
    _project(project_id)
    filename = re.sub(r"[^\w.() -]+", "_", file.filename or "upload.bin").strip(". ") or "upload.bin"
    file_id = str(uuid.uuid4())
    project_dir = DATA_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    target = project_dir / f"{file_id}_{filename}"
    size = 0
    with target.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 100 * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file exceeds 100 MB limit")
            output.write(chunk)
    item = {
        "id": file_id,
        "project_id": project_id,
        "filename": filename,
        "path": str(target),
        "media_type": file.content_type,
        "kind": kind,
        "size": size,
        "created_at": now(),
    }
    store.put("files", "id", file_id, item, project_id)
    return item


@app.put("/api/v1/projects/{project_id}/model", tags=["Projects"], summary="Select model for project")
def select_model(project_id: str, selection: ModelSelection) -> dict:
    project = _project(project_id)
    project["model"] = selection.model_dump()
    project["updated_at"] = now()
    store.put("projects", "id", project_id, project)
    return project["model"]


async def _execute_run(project_id: str, run_id: str, request: RunRequest) -> None:
    project = _project(project_id)
    run = store.get("runs", "id", run_id) or {}

    def stage(name: str, progress: int) -> None:
        run.update({"status": "running", "stage": name, "progress_pct": progress, "updated_at": now()})
        store.put("runs", "id", run_id, run, project_id)

    try:
        stage("ingestion", 10)
        files = [{key: item[key] for key in ("id", "filename", "path", "media_type", "kind")} for item in _files(project_id)]
        ingestion = await post_json(INGESTION_URL, "/api/v1/ingestions", {
            "project_id": project_id, "domain": project["domain"], "files": files,
        })

        stage("retrieval", 35)
        knowledge = await post_json(KNOWLEDGE_URL, "/api/v1/context", {
            "project_id": project_id, "domain": project["domain"], "files": files, "ingestion": ingestion,
        })

        stage("generation", 55)
        model = dict(project["model"])
        if request.use_llm is not None:
            model["enabled"] = request.use_llm
        result = await post_json(HYPOTHESIS_URL, "/api/v1/generations", {
            "project_id": project_id,
            "domain": project["domain"],
            "target_kpi": project["target_kpi"],
            "constraints": project["constraints"],
            "ingestion": ingestion,
            "knowledge": knowledge,
            "model": model,
            "weights": request.weights,
            "feedback": _feedback(project_id),
        }, timeout=360)

        stage("graph", 85)
        graph = await post_json(KNOWLEDGE_URL, "/api/v1/graphs", {
            "project": project, "ingestion": ingestion, "hypotheses": result["hypotheses"],
        })
        store.put("results", "project_id", project_id, result)
        store.put("graphs", "project_id", project_id, graph)
        run.update({"status": "done", "stage": "done", "progress_pct": 100, "error": None, "updated_at": now()})
        project.update({"status": "done", "engine": result.get("engine"), "updated_at": now()})
    except Exception as exc:
        run.update({"status": "error", "stage": run.get("stage", "unknown"), "error": str(exc), "updated_at": now()})
        project.update({"status": "error", "updated_at": now()})
    store.put("runs", "id", run_id, run, project_id)
    store.put("projects", "id", project_id, project)


@app.post("/api/v1/projects/{project_id}/runs", tags=["Runs"], status_code=202, summary="Start generation pipeline")
def start_run(project_id: str, request: RunRequest, background: BackgroundTasks) -> dict:
    project = _project(project_id)
    if not _files(project_id):
        raise HTTPException(status_code=409, detail="upload at least one source file before starting a run")
    active = next((run for run in store.list("runs", project_id) if run["status"] in {"queued", "running"}), None)
    if active:
        raise HTTPException(status_code=409, detail=f"run {active['id']} is already active")
    run_id = str(uuid.uuid4())
    run = {
        "id": run_id,
        "project_id": project_id,
        "status": "queued",
        "stage": "queued",
        "progress_pct": 0,
        "error": None,
        "created_at": now(),
        "updated_at": now(),
    }
    store.put("runs", "id", run_id, run, project_id)
    project.update({"status": "running", "updated_at": now()})
    store.put("projects", "id", project_id, project)
    background.add_task(_execute_run, project_id, run_id, request)
    return run


@app.get("/api/v1/runs/{run_id}", tags=["Runs"], summary="Get run status")
def get_run(run_id: str) -> dict:
    run = store.get("runs", "id", run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.get("/api/v1/projects/{project_id}/hypotheses", tags=["Hypotheses"], summary="List ranked hypotheses")
def hypotheses(
    project_id: str,
    min_priority: float = Query(0, ge=-100, le=100),
    max_risk: int = Query(5, ge=1, le=5),
    category: str | None = None,
) -> dict:
    result = _result(project_id)
    items = [item for item in result["hypotheses"] if item.get("scores", {}).get("priority", 0) >= min_priority and item.get("scores", {}).get("risk", 5) <= max_risk]
    if category:
        items = [item for item in items if category in item.get("categories", [])]
    return {"items": items, "total": len(items), "engine": result.get("engine"), "summary": result.get("summary", {}), "warnings": result.get("warnings", [])}


@app.get("/api/v1/hypotheses/{hypothesis_id}", tags=["Hypotheses"], summary="Get hypothesis card")
def get_hypothesis(hypothesis_id: str, project_id: str = Query(...)) -> dict:
    item = next((item for item in _result(project_id)["hypotheses"] if item["id"] == hypothesis_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="hypothesis not found")
    return item | {"feedback": _feedback(project_id).get(hypothesis_id)}


@app.put("/api/v1/hypotheses/{hypothesis_id}/feedback", tags=["Hypotheses"], summary="Upsert expert feedback")
async def put_feedback(hypothesis_id: str, payload: FeedbackRequest, project_id: str = Query(...)) -> dict:
    result = _result(project_id)
    if not any(item["id"] == hypothesis_id for item in result["hypotheses"]):
        raise HTTPException(status_code=404, detail="hypothesis not found")
    item = {"hypothesis_id": hypothesis_id, "project_id": project_id, **payload.model_dump(), "updated_at": now()}
    store.put("feedback", "hypothesis_id", hypothesis_id, item, project_id)
    ranked = await post_json(HYPOTHESIS_URL, "/api/v1/rankings", {
        "hypotheses": result["hypotheses"], "weights": {}, "feedback": _feedback(project_id),
    })
    result["hypotheses"] = ranked["hypotheses"]
    store.put("results", "project_id", project_id, result)
    return item


@app.post("/api/v1/projects/{project_id}/rerank", tags=["Hypotheses"], summary="Re-rank with expert weights")
async def rerank(project_id: str, payload: RerankRequest) -> dict:
    result = _result(project_id)
    ranked = await post_json(HYPOTHESIS_URL, "/api/v1/rankings", {
        "hypotheses": result["hypotheses"], "weights": payload.weights, "feedback": _feedback(project_id),
    })
    result["hypotheses"] = ranked["hypotheses"]
    store.put("results", "project_id", project_id, result)
    return {"items": result["hypotheses"]}


@app.get("/api/v1/projects/{project_id}/graph", tags=["Knowledge"], summary="Get knowledge graph")
def graph(project_id: str) -> dict:
    value = store.get("graphs", "project_id", project_id)
    if not value:
        raise HTTPException(status_code=404, detail="project graph not found")
    return value


@app.get("/api/v1/hypotheses/{hypothesis_id}/trace", tags=["Knowledge"], summary="Get evidence trace")
def trace(hypothesis_id: str, project_id: str = Query(...), depth: int = Query(2, ge=1, le=5)) -> dict:
    value = graph(project_id)
    start = f"hypothesis:{hypothesis_id}"
    nodes = {node["id"]: node for node in value["nodes"]}
    if start not in nodes:
        raise HTTPException(status_code=404, detail="trace not found")
    adjacent: dict[str, list[str]] = defaultdict(list)
    for edge in value["edges"]:
        adjacent[edge["from"]].append(edge["to"])
        adjacent[edge["to"]].append(edge["from"])
    keep, queue = {start}, deque([(start, 0)])
    while queue:
        node, level = queue.popleft()
        if level == depth:
            continue
        for neighbor in adjacent[node]:
            if neighbor not in keep:
                keep.add(neighbor)
                queue.append((neighbor, level + 1))
    return {"nodes": [nodes[node] for node in keep], "edges": [edge for edge in value["edges"] if edge["from"] in keep and edge["to"] in keep]}


def _export_markdown(project: dict, result: dict) -> str:
    lines = [f"# {project['title']}", "", f"Целевой KPI: **{project['target_kpi']}**", "", f"Движок: `{result.get('engine', 'rule-based')}`", "", "## Гипотезы", ""]
    for item in result["hypotheses"]:
        lines.extend([
            f"### {item['rank']}. {item['title']}", "",
            f"Приоритет: **{item['scores']['priority']}**", "",
            item["hypothesis"], "", f"Механизм: {item.get('mechanism', '—')}", "",
            "План проверки:", *[f"{index}. {step}" for index, step in enumerate(item.get("roadmap", []), 1)], "",
        ])
    return "\n".join(lines)


@app.get("/api/v1/projects/{project_id}/export", tags=["Export"], summary="Export project report")
def export(project_id: str, format: str = Query("json", pattern="^(json|csv|md)$")) -> Response:
    project, result = _project(project_id), _result(project_id)
    if format == "json":
        body, media, suffix = json.dumps(result, ensure_ascii=False, indent=2).encode(), "application/json", "json"
    elif format == "md":
        body, media, suffix = _export_markdown(project, result).encode(), "text/markdown; charset=utf-8", "md"
    else:
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["rank", "priority", "title", "category", "hypothesis", "risk", "feasibility", "novelty"])
        for item in result["hypotheses"]:
            scores = item["scores"]
            writer.writerow([item["rank"], scores["priority"], item["title"], item.get("category_ru"), item["hypothesis"], scores.get("risk"), scores.get("feasibility"), scores.get("novelty")])
        body, media, suffix = ("\ufeff" + output.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", "csv"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="project-{project_id}.{suffix}"'})

