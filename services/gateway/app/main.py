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
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from hf_contracts import PlantResult
from pydantic import BaseModel

from . import clients
from .evaluation import evaluate
from .exporters import to_csv, to_docx, to_json, to_markdown
from .graph import build_graph, merge_patch

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output"))
STATE_FILE = OUTPUT_DIR / "state.json"
# HF_PERSIST=0 — полностью безфайловый режим: всё в памяти до перезапуска
PERSIST = os.environ.get("HF_PERSIST", "1") not in ("0", "false", "no")
# HF_API_KEY — если задан, все запросы (кроме health) требуют X-API-Key
API_KEY = os.environ.get("HF_API_KEY") or None

app = FastAPI(
    title="Фабрика гипотез — API",
    description="Генерация и приоритизация технологических гипотез снижения "
    "потерь цветных металлов с хвостами флотации (хакатон Норникеля, задача 1).",
    version="1.1.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.middleware("http")
async def _auth(request: Request, call_next):
    """Разграничение доступа (ТЗ: безопасность): API-ключ через env HF_API_KEY."""
    if (API_KEY and request.method != "OPTIONS"
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/v1/health"
            and request.headers.get("x-api-key") != API_KEY):
        return JSONResponse({"detail": "Требуется заголовок X-API-Key"},
                            status_code=401)
    return await call_next(request)

# plant -> результат конвейера / правки графа; всё состояние — в памяти,
# state.json — единственный файл (только снапшот для рестарта)
_results: dict[str, dict] = {}
_graph_patch: dict[str, dict] = {}
_feedback: dict[str, dict] = {}
_evaluation: dict = {}
_weights: dict = {}  # пользовательские веса ранжирования (ТЗ 8.2)

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


class Weights(BaseModel):
    """Веса критериев ранжирования (эксперт, ТЗ 8.2). Нормируются к сумме 1."""
    impact: float = 0.40
    feasibility: float = 0.30
    risk: float = 0.20
    novelty: float = 0.10


def _persist():
    if not PERSIST:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"results": _results, "graph_patch": _graph_patch,
                    "feedback": _feedback, "evaluation": _evaluation,
                    "weights": _weights},
                   ensure_ascii=False), encoding="utf-8")


@app.on_event("startup")
def _load_state():
    global _results, _graph_patch, _feedback, _evaluation, _weights
    if PERSIST and STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if "results" in state:
            _results = state["results"]
            _graph_patch = state.get("graph_patch", {})
            _feedback = state.get("feedback", {})
            _evaluation = state.get("evaluation", {})
            _weights = state.get("weights", {})
        else:  # старый формат: плоский dict результатов
            _results = state


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
        result = clients.generate(parsed, use_llm, _feedback or None, project,
                                  _weights or None)
        _results[result["plant"]] = result

    global _evaluation
    _evaluation = evaluate(_results, DATA_DIR)
    _persist()
    return RunSummary(plants=sorted(_results),
                      engine={p: r["engine"] for p, r in _results.items()},
                      evaluation=_evaluation)


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
    result = clients.generate(parsed, use_llm, _feedback or None, project,
                              _weights or None)
    _results[result["plant"]] = result
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
                                          _feedback or None, _weights or None)
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
    # обучение на валидации: подтверждённые/отклонённые меняют ранжирование
    result["hypotheses"] = clients.rerank(result["hypotheses"],
                                          _feedback or None, _weights or None)
    _persist()
    return next(h for h in result["hypotheses"] if h["id"] == hyp_id)


@app.delete("/api/v1/plants/{plant}/hypotheses/{hyp_id}")
def delete_hypothesis(plant: str, hyp_id: str) -> dict:
    result = _get(plant)
    before = len(result["hypotheses"])
    result["hypotheses"] = [h for h in result["hypotheses"] if h["id"] != hyp_id]
    if len(result["hypotheses"]) == before:
        raise HTTPException(404, f"Гипотеза {hyp_id} не найдена")
    result["hypotheses"] = clients.rerank(result["hypotheses"],
                                          _feedback or None, _weights or None)
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


# -------------------------------------------- веса, что-если, фидбэк, экспорт
@app.get("/api/v1/weights", response_model=Weights)
def get_weights() -> Weights:
    return Weights(**_weights) if _weights else Weights()


@app.put("/api/v1/weights", response_model=Weights)
def set_weights(w: Weights) -> Weights:
    """Экспертная настройка весов ранжирования + переранжирование всего."""
    global _weights
    if any(v < 0 for v in w.model_dump().values()) or \
            sum(w.model_dump().values()) <= 0:
        raise HTTPException(400, "Веса неотрицательны, сумма > 0")
    _weights = w.model_dump()
    for result in _results.values():
        result["hypotheses"] = clients.rerank(result["hypotheses"],
                                              _feedback or None, _weights)
    _persist()
    return w


@app.get("/api/v1/plants/{plant}/whatif")
def whatif(plant: str, signal: str,
           reduction_pct: float = Query(50.0, ge=0, le=100)) -> dict:
    """Контрфактуальный анализ: «если устранить N% потерь сигнала S,
    насколько снизятся потери с хвостами»."""
    result = _get(plant)
    return clients.whatif(_diagnosis_of(result), signal, reduction_pct)


@app.post("/api/v1/feedback")
def feedback(vote: FeedbackVote) -> dict:
    """Голос эксперта 👍/👎 по категории мероприятия + переранжирование."""
    if vote.vote not in ("up", "down"):
        raise HTTPException(400, "vote: up | down")
    cat = _feedback.setdefault(vote.category, {"up": 0, "down": 0})
    cat[vote.vote] += 1
    for result in _results.values():
        result["hypotheses"] = clients.rerank(result["hypotheses"], _feedback,
                                              _weights or None)
    _persist()
    return {"feedback": _feedback}


@app.get("/api/v1/feedback")
def get_feedback() -> dict:
    return _feedback


@app.get("/api/v1/evaluation")
def evaluation() -> dict:
    if not _evaluation:
        raise HTTPException(404, "Оценка ещё не рассчитана — POST /api/v1/runs")
    return _evaluation


@app.get("/api/v1/plants/{plant}/export")
def export(plant: str, fmt: str = Query("json", pattern="^(json|csv|md|docx)$"),
           lang: str = Query("ru", pattern="^(ru|en|zh)$")):
    """Экспорт формируется на лету. lang=en|zh переводит md/docx-отчёт
    через LLM-слой (мультиязычность из ТЗ; требует доступного провайдера)."""
    result = _get(plant)
    stem = plant.replace(" ", "_")
    if fmt == "docx":
        body = to_docx(result)
        return Response(
            body,
            media_type="application/vnd.openxmlformats-officedocument"
                       ".wordprocessingml.document",
            headers={"Content-Disposition":
                     f"attachment; filename*=UTF-8''{quote(f'report_{stem}.docx')}"})
    if fmt == "json":
        content, media, name = to_json(result), "application/json", f"hypotheses_{stem}.json"
    elif fmt == "csv":
        # utf-8-sig — чтобы Excel корректно открыл кириллицу
        content, media, name = to_csv(result), "text/csv; charset=utf-8", f"hypotheses_{stem}.csv"
    else:
        content, media, name = to_markdown(result), "text/markdown; charset=utf-8", f"report_{stem}.md"
    if lang != "ru" and fmt == "md":
        translated = clients.llm_translate([content], lang)
        if not translated:
            raise HTTPException(503, "Перевод недоступен: LLM-провайдер "
                                     "отключён или без ключа (LLM_PROVIDER)")
        content = translated[0]
        name = name.replace(".md", f".{lang}.md")
    body = content.encode("utf-8-sig" if fmt == "csv" else "utf-8")
    return Response(body, media_type=media, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
