"""Generation-сервис: диагностика потерь + генерация и ранжирование гипотез.

Базу знаний берёт у knowledge-сервиса, LLM-усиление — у llm-сервиса
(оба адреса через env). Работает и без них: без kb вернёт 503, без llm —
rule-based результат.
"""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .analyze import analyze_hypothesis
from .diagnosis import diagnose
from .generator import generate, rank

KNOWLEDGE_URL = os.environ.get("KNOWLEDGE_URL", "http://localhost:8002")

app = FastAPI(
    title="HF Generation Service",
    description="Правила физики обогащения -> находки с тоннами; сигналы × каталог "
    "практик -> карточки гипотез; ранжирование 0.40·эффект + 0.30·реализуемость + "
    "0.20·(1-риск) + 0.10·новизна + фидбэк эксперта + штраф за однотипность.",
    version="1.0.0",
)


class DiagnoseRequest(BaseModel):
    parsed: dict


class GenerateRequest(BaseModel):
    parsed: dict
    use_llm: bool = True
    feedback: dict | None = None
    project: dict | None = None  # {"target_kpi": str, "constraints": [str]}
    weights: dict | None = None  # {"impact":.4,"feasibility":.3,"risk":.2,"novelty":.1}


class AnalyzeRequest(BaseModel):
    """Произвольная гипотеза эксперта поверх готовой диагностики."""
    diagnosis: dict  # plant, summary, findings, cells
    text: str
    title: str | None = None
    category: str | None = None
    seq: int = 0


class RerankRequest(BaseModel):
    hypotheses: list[dict]
    feedback: dict | None = None
    weights: dict | None = None


class WhatIfRequest(BaseModel):
    """Контрфактуальный анализ: «если устранить X% потерь сигнала S»."""
    diagnosis: dict  # cells, findings, summary
    signal: str
    reduction_pct: float = 50.0


def _fetch_kb() -> dict:
    try:
        r = httpx.get(f"{KNOWLEDGE_URL}/api/v1/kb", timeout=30.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(503, f"knowledge-сервис недоступен: {e}") from e


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "service": "generation"}


@app.post("/api/v1/diagnose")
def diagnose_endpoint(req: DiagnoseRequest) -> dict:
    return diagnose(req.parsed)


@app.post("/api/v1/generate")
def generate_endpoint(req: GenerateRequest) -> dict:
    kb = _fetch_kb()
    diagnosis = diagnose(req.parsed)
    return generate(diagnosis, kb, use_llm=req.use_llm, feedback=req.feedback,
                    project=req.project, weights=req.weights)


@app.post("/api/v1/analyze")
def analyze_endpoint(req: AnalyzeRequest) -> dict:
    kb = _fetch_kb()
    return analyze_hypothesis(req.diagnosis, kb, req.text,
                              title=req.title, category=req.category,
                              seq=req.seq)


@app.post("/api/v1/rerank")
def rerank_endpoint(req: RerankRequest) -> list[dict]:
    hyps = req.hypotheses
    rank(hyps, req.feedback, req.weights)
    return hyps


@app.post("/api/v1/whatif")
def whatif_endpoint(req: WhatIfRequest) -> dict:
    """Контрфактуальный расчёт по ячейкам отчёта: адресуемый металл сигнала
    и эффект на KPI при устранении заданной доли потерь."""
    from .generator import SIGNAL_CELLS, comp_ids
    pred = SIGNAL_CELLS.get(req.signal)
    if pred is None:
        raise HTTPException(400, f"Неизвестный сигнал: {req.signal}. "
                                 f"Доступны: {sorted(SIGNAL_CELLS)}")
    pct = max(0.0, min(100.0, req.reduction_pct))
    tons = {el: 0.0 for el in comp_ids(req.diagnosis)}
    for cell in req.diagnosis.get("cells", []):
        if pred(cell):
            tons[cell["el"]] = tons.get(cell["el"], 0.0) + cell["tons"]
    summary = req.diagnosis.get("summary", {})
    losses = summary.get("losses_t") or {
        el: summary.get(f"losses_{el}_t", 0) for el in tons}
    delta = {el: round(t * pct / 100, 1) for el, t in tons.items()}
    return {
        "signal": req.signal,
        "reduction_pct": pct,
        "addressable_t": {el: round(t, 1) for el, t in tons.items()},
        "kpi_delta_t": delta,
        "losses_after_t": {
            el: round((losses.get(el) or 0) - delta[el], 1) for el in tons},
        "note": "Контрфактуальная оценка по ячейкам отчёта (поток × класс × "
                "форма); допущение линейного устранения потерь.",
    }
