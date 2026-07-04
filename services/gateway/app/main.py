"""API Gateway «Фабрики гипотез».

Публичный REST API (OpenAPI — /docs, /openapi.json): интерактивная R&D-задача
(KPI + ограничения), запуск конвейера по каталогу данных или по загруженному
отчёту, гипотезы (включая произвольные гипотезы эксперта), корректировка графа
знаний, фидбэк с переранжированием, экспорт JSON/CSV/MD, leave-one-out оценка.

Оркестрация: ingestion (парсинг xlsx) -> generation (диагностика + гипотезы;
внутри — knowledge и llm сервисы). Результаты хранятся в OUTPUT_DIR.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from hf_contracts import PlantResult
from pydantic import BaseModel

from . import clients
from .evaluation import evaluate
from .exporters import export_all
from .graph import build_graph, merge_patch

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output"))
STATE_FILE = OUTPUT_DIR / "state.json"
FEEDBACK_FILE = OUTPUT_DIR / "feedback.json"

app = FastAPI(
    title="Фабрика гипотез — API",
    description="Генерация и приоритизация технологических гипотез снижения "
    "потерь цветных металлов с хвостами флотации (хакатон Норникеля, задача 1).",
    version="1.1.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

# plant -> результат конвейера / правки графа
_results: dict[str, dict] = {}
_graph_patch: dict[str, dict] = {}
_feedback: dict[str, dict] = {}

HYP_STATUSES = {"confirmed", "rejected", "catalog", "generated", "llm",
                "llm-new", "expert_added"}


class RunOptions(BaseModel):
    """Интерактивный ввод R&D-задачи (ТЗ 5.1)."""
    target_kpi: str | None = None
    constraints: list[str] = []


class FeedbackVote(BaseModel):
    category: str  # GRIND | CLASSIFY | REGRIND | FLOT | REAGENT | CRUSH | TAILS | AUTO
    vote: str      # up | down


class NewHypothesis(BaseModel):
    """Произвольная гипотеза эксперта — обрабатывается как любая другая."""
    text: str
    title: str | None = None
    category: str | None = None


class HypothesisStatus(BaseModel):
    status: str  # confirmed | rejected


class GraphDelta(BaseModel):
    removed_nodes: list[str] = []
    removed_edges: list[str] = []
    added_edges: list[dict] = []  # [{"from": id, "to": id}]


class RunSummary(BaseModel):
    plants: list[str]
    engine: dict[str, str]
    evaluation: dict


def _persist():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"results": _results, "graph_patch": _graph_patch},
                   ensure_ascii=False), encoding="utf-8")
    FEEDBACK_FILE.write_text(json.dumps(_feedback, ensure_ascii=False, indent=2),
                             encoding="utf-8")


@app.on_event("startup")
def _load_state():
    global _results, _graph_patch, _feedback
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if "results" in state:
            _results = state["results"]
            _graph_patch = state.get("graph_patch", {})
        else:  # старый формат: плоский dict результатов
            _results = state
    if FEEDBACK_FILE.exists():
        _feedback = json.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))


def _get(plant: str) -> dict:
    if plant not in _results:
        raise HTTPException(404, f"Нет результатов по фабрике «{plant}». "
                                 f"Запустите POST /api/v1/runs")
    return _results[plant]


def _diagnosis_of(result: dict) -> dict:
    return {k: result[k] for k in ("plant", "summary", "findings", "cells")}


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "service": "gateway",
            "downstream": clients.services_health(),
            "plants_loaded": sorted(_results)}


# ------------------------------------------------------------------- запуски
@app.post("/api/v1/runs", response_model=RunSummary)
def run_batch(use_llm: bool = Query(True),
              options: RunOptions | None = None) -> RunSummary:
    """Полный прогон всех отчётов из DATA_DIR. body (опц.): KPI и ограничения."""
    if not DATA_DIR.exists():
        raise HTTPException(404, f"DATA_DIR не найден: {DATA_DIR}")
    xlsx_files = sorted(DATA_DIR.glob("Пример */Хвосты*.xlsx"))
    if not xlsx_files:
        raise HTTPException(404, f"В {DATA_DIR} нет отчётов 'Пример */Хвосты*.xlsx'")
    project = options.model_dump() if options and options.target_kpi else None

    for xlsx in xlsx_files:
        parsed = clients.parse_xlsx(xlsx.name, xlsx.read_bytes())
        result = clients.generate(parsed, use_llm, _feedback or None, project)
        _results[result["plant"]] = result
        export_all(result, OUTPUT_DIR / "export")

    ev = evaluate(_results, DATA_DIR)
    (OUTPUT_DIR / "evaluation.json").write_text(
        json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    _persist()
    return RunSummary(plants=sorted(_results),
                      engine={p: r["engine"] for p, r in _results.items()},
                      evaluation=ev)


@app.post("/api/v1/reports", response_model=PlantResult)
async def run_uploaded(use_llm: bool = Query(True),
                       file: UploadFile = File(...),
                       target_kpi: str = Form(""),
                       constraints: str = Form("")) -> dict:
    """Конвейер для загруженного отчёта + интерактивные KPI/ограничения."""
    project = None
    if target_kpi.strip() or constraints.strip():
        project = {"target_kpi": target_kpi.strip() or None,
                   "constraints": [c.strip() for c in constraints.splitlines()
                                   if c.strip()]}
    parsed = clients.parse_xlsx(file.filename or "report.xlsx", await file.read())
    result = clients.generate(parsed, use_llm, _feedback or None, project)
    _results[result["plant"]] = result
    export_all(result, OUTPUT_DIR / "export")
    _persist()
    return result


# ------------------------------------------------------------------ гипотезы
@app.get("/api/v1/plants")
def plants() -> list[dict]:
    return [{"plant": p, "engine": r["engine"], "summary": r["summary"],
             "project": r.get("project"),
             "hypotheses_count": len(r["hypotheses"])}
            for p, r in sorted(_results.items())]


@app.get("/api/v1/plants/{plant}", response_model=PlantResult)
def plant_result(plant: str) -> dict:
    return _get(plant)


@app.get("/api/v1/plants/{plant}/hypotheses")
def plant_hypotheses(plant: str) -> list[dict]:
    return _get(plant)["hypotheses"]


@app.post("/api/v1/plants/{plant}/hypotheses")
def add_hypothesis(plant: str, req: NewHypothesis) -> dict:
    """Произвольная гипотеза эксперта: категория, адресуемый металл,
    обоснование и место в общем ранжировании определяются системой."""
    result = _get(plant)
    if not req.text.strip():
        raise HTTPException(400, "Пустой текст гипотезы")
    seq = sum(1 for h in result["hypotheses"]
              if h["status"] == "expert_added") + 1
    card = clients.analyze_hypothesis(_diagnosis_of(result), req.text,
                                      req.title, req.category, seq)
    result["hypotheses"].append(card)
    result["hypotheses"] = clients.rerank(result["hypotheses"],
                                          _feedback or None)
    _persist()
    return next(h for h in result["hypotheses"] if h["id"] == card["id"])


@app.patch("/api/v1/plants/{plant}/hypotheses/{hyp_id}")
def set_hypothesis_status(plant: str, hyp_id: str, req: HypothesisStatus) -> dict:
    """Экспертная валидация: подтвердить / отклонить гипотезу (ТЗ 8.4)."""
    if req.status not in ("confirmed", "rejected"):
        raise HTTPException(400, "status: confirmed | rejected")
    result = _get(plant)
    hyp = next((h for h in result["hypotheses"] if h["id"] == hyp_id), None)
    if hyp is None:
        raise HTTPException(404, f"Гипотеза {hyp_id} не найдена")
    hyp["status"] = req.status
    _persist()
    return hyp


@app.delete("/api/v1/plants/{plant}/hypotheses/{hyp_id}")
def delete_hypothesis(plant: str, hyp_id: str) -> dict:
    result = _get(plant)
    before = len(result["hypotheses"])
    result["hypotheses"] = [h for h in result["hypotheses"] if h["id"] != hyp_id]
    if len(result["hypotheses"]) == before:
        raise HTTPException(404, f"Гипотеза {hyp_id} не найдена")
    result["hypotheses"] = clients.rerank(result["hypotheses"],
                                          _feedback or None)
    _persist()
    return {"deleted": hyp_id}


# --------------------------------------------------------------- граф знаний
@app.get("/api/v1/plants/{plant}/graph")
def plant_graph(plant: str) -> dict:
    return build_graph(_get(plant), _graph_patch.get(plant))


@app.post("/api/v1/plants/{plant}/graph/patch")
def patch_graph(plant: str, delta: GraphDelta) -> dict:
    """Корректировка графа экспертом: удаление узлов/рёбер, новые связи.
    Правки хранятся отдельно и переживают повторную генерацию."""
    _get(plant)
    _graph_patch[plant] = merge_patch(_graph_patch.get(plant),
                                      delta.model_dump())
    _persist()
    return build_graph(_results[plant], _graph_patch[plant])


@app.delete("/api/v1/plants/{plant}/graph/patch")
def reset_graph(plant: str) -> dict:
    _graph_patch.pop(plant, None)
    _persist()
    return build_graph(_get(plant), None)


# ------------------------------------------------------- фидбэк, оценка, экспорт
@app.post("/api/v1/feedback")
def feedback(vote: FeedbackVote) -> dict:
    """Голос эксперта 👍/👎 по категории мероприятия + переранжирование."""
    if vote.vote not in ("up", "down"):
        raise HTTPException(400, "vote: up | down")
    cat = _feedback.setdefault(vote.category, {"up": 0, "down": 0})
    cat[vote.vote] += 1
    for result in _results.values():
        result["hypotheses"] = clients.rerank(result["hypotheses"], _feedback)
    _persist()
    return {"feedback": _feedback}


@app.get("/api/v1/feedback")
def get_feedback() -> dict:
    return _feedback


@app.get("/api/v1/evaluation")
def evaluation() -> dict:
    path = OUTPUT_DIR / "evaluation.json"
    if not path.exists():
        raise HTTPException(404, "Оценка ещё не рассчитана — POST /api/v1/runs")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/v1/plants/{plant}/export")
def export(plant: str, fmt: str = Query("json", pattern="^(json|csv|md)$")):
    result = _get(plant)
    paths = export_all(result, OUTPUT_DIR / "export")
    media = {"json": "application/json", "csv": "text/csv",
             "md": "text/markdown"}[fmt]
    return FileResponse(paths[fmt], media_type=media,
                        filename=Path(paths[fmt]).name)
