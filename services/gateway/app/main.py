"""API Gateway «Фабрики гипотез».

Публичный REST API (OpenAPI — /docs, /openapi.json): запуск конвейера по
каталогу данных или по загруженному отчёту, гипотезы, экспертный фидбэк с
переранжированием, экспорт JSON/CSV/MD, leave-one-out оценка против эталона.

Оркестрация: ingestion (парсинг xlsx) -> generation (диагностика + гипотезы;
внутри — knowledge и llm сервисы). Результаты хранятся в OUTPUT_DIR.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from hf_contracts import PlantResult
from pydantic import BaseModel

from . import clients
from .evaluation import evaluate
from .exporters import export_all

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output"))
STATE_FILE = OUTPUT_DIR / "state.json"
FEEDBACK_FILE = OUTPUT_DIR / "feedback.json"

app = FastAPI(
    title="Фабрика гипотез — API",
    description="Генерация и приоритизация технологических гипотез снижения "
    "потерь цветных металлов с хвостами флотации (хакатон Норникеля, задача 1).",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

# plant -> результат конвейера
_results: dict[str, dict] = {}
_feedback: dict[str, dict] = {}


class FeedbackVote(BaseModel):
    category: str  # GRIND | CLASSIFY | REGRIND | FLOT | REAGENT | CRUSH | TAILS | AUTO
    vote: str      # up | down


class RunSummary(BaseModel):
    plants: list[str]
    engine: dict[str, str]
    evaluation: dict


def _persist():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(_results, ensure_ascii=False),
                          encoding="utf-8")
    FEEDBACK_FILE.write_text(json.dumps(_feedback, ensure_ascii=False, indent=2),
                             encoding="utf-8")


@app.on_event("startup")
def _load_state():
    global _results, _feedback
    if STATE_FILE.exists():
        _results = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if FEEDBACK_FILE.exists():
        _feedback = json.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "service": "gateway",
            "downstream": clients.services_health(),
            "plants_loaded": sorted(_results)}


@app.post("/api/v1/runs", response_model=RunSummary)
def run_batch(use_llm: bool = Query(True)) -> RunSummary:
    """Полный прогон: все отчёты «Хвосты *.xlsx» из DATA_DIR."""
    if not DATA_DIR.exists():
        raise HTTPException(404, f"DATA_DIR не найден: {DATA_DIR}")
    xlsx_files = sorted(DATA_DIR.glob("Пример */Хвосты*.xlsx"))
    if not xlsx_files:
        raise HTTPException(404, f"В {DATA_DIR} нет отчётов 'Пример */Хвосты*.xlsx'")

    for xlsx in xlsx_files:
        parsed = clients.parse_xlsx(xlsx.name, xlsx.read_bytes())
        result = clients.generate(parsed, use_llm, _feedback or None)
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
                       file: UploadFile = File(...)) -> dict:
    """Конвейер для одного загруженного отчёта (xlsx)."""
    parsed = clients.parse_xlsx(file.filename or "report.xlsx", await file.read())
    result = clients.generate(parsed, use_llm, _feedback or None)
    _results[result["plant"]] = result
    export_all(result, OUTPUT_DIR / "export")
    _persist()
    return result


@app.get("/api/v1/plants")
def plants() -> list[dict]:
    return [{"plant": p, "engine": r["engine"], "summary": r["summary"],
             "hypotheses_count": len(r["hypotheses"])}
            for p, r in sorted(_results.items())]


def _get(plant: str) -> dict:
    if plant not in _results:
        raise HTTPException(404, f"Нет результатов по фабрике «{plant}». "
                                 f"Запустите POST /api/v1/runs")
    return _results[plant]


@app.get("/api/v1/plants/{plant}", response_model=PlantResult)
def plant_result(plant: str) -> dict:
    return _get(plant)


@app.get("/api/v1/plants/{plant}/hypotheses")
def plant_hypotheses(plant: str) -> list[dict]:
    return _get(plant)["hypotheses"]


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
