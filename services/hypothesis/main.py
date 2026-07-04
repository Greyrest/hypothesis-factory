from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import FastAPI
from pydantic import Field

from services.common.config import MODEL_RUNTIME_URL
from services.common.health import health
from services.common.http import post_json
from services.common.models import GenerationRequest, StrictModel

app = FastAPI(
    title="Hypothesis Factory · Hypothesis Service",
    version="2.0.0",
    description="Generates falsifiable hypotheses and ranks them independently of storage and UI.",
)


class RerankPayload(StrictModel):
    hypotheses: list[dict[str, Any]]
    weights: dict[str, float] = Field(default_factory=dict)
    feedback: dict[str, dict[str, Any]] = Field(default_factory=dict)


@app.get("/api/v1/health", tags=["System"])
def service_health() -> dict:
    return health("hypothesis")


def _generic_generate(request: GenerationRequest) -> list[dict]:
    chunks = request.knowledge.get("chunks", [])
    hypotheses = []
    for index, chunk in enumerate(chunks[:6], 1):
        fact = chunk.get("text", "")[:500]
        if not fact:
            continue
        hypotheses.append({
            "id": f"{request.project_id}-generic-{index}",
            "rank": index,
            "title": f"Проверка фактора из источника {index}",
            "hypothesis": (
                f"Если экспериментально изменить фактор, описанный в источнике «{chunk.get('source', 'данные')}», "
                f"то KPI «{request.target_kpi}» изменится измеримо; направление и величина должны быть установлены контролируемым опытом."
            ),
            "categories": ["EXPERIMENT"],
            "category_ru": "Эксперимент",
            "equipment": "",
            "streams": [],
            "mechanism": "Механизм формулируется как проверяемая причинная связь на основании загруженного факта.",
            "evidence": [{"source": chunk.get("source", "Загруженный источник"), "fact": fact}],
            "expected_effect": {
                "addressable_t": {"ni": 0, "cu": 0},
                "uplift_pct": [0, 0],
                "kpi_delta_t": {"ni": [0, 0], "cu": [0, 0]},
                "kpi": request.target_kpi,
                "assumption": "Количественный эффект неизвестен до скринингового эксперимента.",
            },
            "scores": {"feasibility": 3, "novelty": 3, "risk": 3, "impact_t": 0, "priority": 50 - index},
            "risks": ["Недостаточно данных для количественной оценки", *request.constraints[:2]],
            "roadmap": ["Определить фактор, контроль и метрику", "Провести скрининговый эксперимент", "Оценить эффект и доверительный интервал"],
            "status": "generated",
            "sources": [chunk.get("source", "Загруженный источник")],
            "matched_signals": [],
            "finding_ids": [],
        })
    return hypotheses


def _merge_enhancements(drafts: list[dict], response: dict) -> list[dict]:
    by_id = {item["id"]: deepcopy(item) for item in drafts}
    for item in response.get("hypotheses", []):
        base = by_id.get(item.get("base_id"))
        if not base:
            continue
        for key in ("title", "hypothesis", "mechanism", "risks", "roadmap"):
            if item.get(key):
                base[key] = item[key]
        for key in ("novelty", "feasibility", "risk"):
            if item.get(key) is not None:
                base["scores"][key] = item[key]
        if item.get("rationale"):
            base["evidence"] = [{
                "source": f"LLM-проверка формулировки ({response.get('engine', 'model')})",
                "fact": item["rationale"],
            }, *base.get("evidence", [])]
        base["status"] = "llm"
    return list(by_id.values())


def _rerank(items: list[dict], weights: dict[str, float], feedback: dict[str, dict]) -> list[dict]:
    result = deepcopy(items)
    defaults = {"impact": .4, "feasibility": .3, "risk": .2, "novelty": .1}
    defaults.update({key: value for key, value in weights.items() if key in defaults})
    max_impact = max((item.get("scores", {}).get("impact_t", 0) for item in result), default=1) or 1
    for item in result:
        scores = item.setdefault("scores", {})
        priority = 100 * (
            defaults["impact"] * scores.get("impact_t", 0) / max_impact
            + defaults["feasibility"] * scores.get("feasibility", 3) / 5
            + defaults["risk"] * (1 - scores.get("risk", 3) / 5)
            + defaults["novelty"] * scores.get("novelty", 3) / 5
        )
        vote = feedback.get(item["id"], {}).get("vote")
        adjustment = 5 if vote == "up" else -5 if vote == "down" else 0
        scores["feedback_adj"] = adjustment
        scores["priority"] = round(priority + adjustment, 1)
    result.sort(key=lambda item: -item["scores"]["priority"])
    for rank, item in enumerate(result, 1):
        item["rank"] = rank
    return result


@app.post("/api/v1/generations", tags=["Generation"], summary="Generate and rank hypotheses")
async def generate_hypotheses(request: GenerationRequest) -> dict:
    diagnosis = request.ingestion.get("diagnosis", {})
    warnings: list[str] = []
    if request.domain == "mining_flotation":
        from generate import rule_based_generate

        drafts = rule_based_generate(diagnosis, request.knowledge)
    else:
        drafts = _generic_generate(request)

    engine = "rule-based"
    usage: dict = {}
    if request.model.enabled and drafts:
        try:
            response = await post_json(MODEL_RUNTIME_URL, "/api/v1/enhance", {
                "selection": request.model.model_dump(),
                "diagnosis": diagnosis,
                "drafts": drafts,
                "knowledge": request.knowledge,
                "language": "ru",
            })
            drafts = _merge_enhancements(drafts, response)
            if any(item.get("status") == "llm" for item in drafts):
                engine = f"rule-based + {response.get('engine')}"
            usage = response.get("usage", {})
        except RuntimeError as exc:
            warnings.append(f"LLM fallback: {exc}")

    hypotheses = _rerank(drafts, request.weights or {}, request.feedback)
    return {
        "project_id": request.project_id,
        "plant": diagnosis.get("plant", request.project_id),
        "engine": engine,
        "summary": request.ingestion.get("summary", {}),
        "hypotheses": hypotheses[:50],
        "findings": diagnosis.get("findings", []),
        "warnings": warnings,
        "usage": usage,
    }


@app.post("/api/v1/rankings", tags=["Ranking"], summary="Re-rank existing hypotheses")
def rerank(payload: RerankPayload) -> dict:
    return {"hypotheses": _rerank(payload.hypotheses, payload.weights, payload.feedback)}

