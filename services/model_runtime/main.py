from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import Field

from services.common.health import health
from services.common.models import ModelSelection, StrictModel

app = FastAPI(
    title="Hypothesis Factory · Model Runtime",
    version="2.0.0",
    description=(
        "Provider-neutral structured generation. API keys remain in this isolated service; "
        "project services only pass provider and model identifiers."
    ),
)

ALLOW_EXTERNAL = os.getenv("HF_ALLOW_EXTERNAL_MODELS", "false").lower() == "true"

MODEL_CATALOG = [
    {"provider": "anthropic", "model": "claude-opus-4-8", "label": "Claude Opus 4.8", "external": True},
    {"provider": "anthropic", "model": "claude-sonnet-4-5", "label": "Claude Sonnet 4.5", "external": True},
    {"provider": "openai", "model": "gpt-5", "label": "OpenAI GPT-5", "external": True},
    {"provider": "ollama", "model": "llama3.3", "label": "Ollama · Llama 3.3", "external": False},
    {"provider": "mock", "model": "deterministic", "label": "Offline deterministic", "external": False},
]


class EnhanceRequest(StrictModel):
    selection: ModelSelection
    diagnosis: dict[str, Any]
    drafts: list[dict[str, Any]]
    knowledge: dict[str, Any]
    language: str = "ru"


def _available(provider: str) -> tuple[bool, str | None]:
    if provider == "anthropic":
        if not ALLOW_EXTERNAL:
            return False, "external models are disabled by HF_ALLOW_EXTERNAL_MODELS"
        return bool(os.getenv("ANTHROPIC_API_KEY")), "ANTHROPIC_API_KEY is not configured"
    if provider == "openai":
        if not ALLOW_EXTERNAL:
            return False, "external models are disabled by HF_ALLOW_EXTERNAL_MODELS"
        return bool(os.getenv("OPENAI_API_KEY")), "OPENAI_API_KEY is not configured"
    return True, None


@app.get("/api/v1/health", tags=["System"])
def service_health() -> dict:
    return health("model-runtime") | {"external_models_enabled": ALLOW_EXTERNAL}


@app.get("/api/v1/models", tags=["Models"], summary="List selectable models")
def list_models() -> dict:
    models = []
    for item in MODEL_CATALOG:
        available, reason = _available(item["provider"])
        models.append(item | {"available": available, "unavailable_reason": None if available else reason})
    return {"models": models, "allow_custom_model": True}


def _context(request: EnhanceRequest) -> dict:
    return {
        "diagnostics": {
            "plant": request.diagnosis.get("plant"),
            "summary": request.diagnosis.get("summary"),
            "findings": request.diagnosis.get("findings", [])[:16],
        },
        "drafts": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "hypothesis": item.get("hypothesis"),
                "effect": item.get("expected_effect"),
            }
            for item in request.drafts[:12]
        ],
        "rules": request.knowledge.get("rules", [])[:20],
    }


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "hypotheses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "base_id": {"type": ["string", "null"]},
                        "title": {"type": "string"},
                        "hypothesis": {"type": "string"},
                        "mechanism": {"type": "string"},
                        "risks": {"type": "array", "items": {"type": "string"}},
                        "roadmap": {"type": "array", "items": {"type": "string"}},
                        "novelty": {"type": "integer", "minimum": 1, "maximum": 5},
                        "feasibility": {"type": "integer", "minimum": 1, "maximum": 5},
                        "risk": {"type": "integer", "minimum": 1, "maximum": 5},
                        "rationale": {"type": "string"},
                    },
                    "required": ["base_id", "title", "hypothesis", "mechanism", "risks", "roadmap", "novelty", "feasibility", "risk", "rationale"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["hypotheses"],
        "additionalProperties": False,
    }


SYSTEM_PROMPT = """You are an R&D engineer. Improve only evidence-backed draft hypotheses.
Every hypothesis must be falsifiable: If <action>, then <measured KPI change>, because <mechanism>.
Do not invent measurements or sources. Preserve quantitative values from context. Return JSON only.
Write in Russian when language is ru."""


async def _anthropic(request: EnhanceRequest) -> tuple[dict, dict]:
    import anthropic

    started = time.monotonic()
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = await client.messages.create(
        model=request.selection.model,
        max_tokens=12000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(_context(request), ensure_ascii=False)}],
        output_config={"format": {"type": "json_schema", "schema": _schema()}},
    )
    text = next((block.text for block in message.content if block.type == "text"), None)
    if not text:
        raise RuntimeError("model returned no text")
    return json.loads(text), {
        "input_tokens": getattr(message.usage, "input_tokens", None),
        "output_tokens": getattr(message.usage, "output_tokens", None),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }


async def _openai(request: EnhanceRequest) -> tuple[dict, dict]:
    base_url = (request.selection.base_url or "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": request.selection.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(_context(request), ensure_ascii=False)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "hypothesis_enhancement", "strict": True, "schema": _schema()},
        },
    }
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json=payload,
        )
        response.raise_for_status()
    body = response.json()
    return json.loads(body["choices"][0]["message"]["content"]), {
        **body.get("usage", {}),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }


async def _ollama(request: EnhanceRequest) -> tuple[dict, dict]:
    base_url = (request.selection.base_url or os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")).rstrip("/")
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(f"{base_url}/api/chat", json={
            "model": request.selection.model,
            "stream": False,
            "format": _schema(),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(_context(request), ensure_ascii=False)},
            ],
        })
        response.raise_for_status()
    body = response.json()
    return json.loads(body["message"]["content"]), {
        "input_tokens": body.get("prompt_eval_count"),
        "output_tokens": body.get("eval_count"),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }


@app.post("/api/v1/enhance", tags=["Models"], summary="Enhance drafts with selected model")
async def enhance(request: EnhanceRequest) -> dict:
    if not request.selection.enabled:
        return {"hypotheses": [], "engine": "disabled", "usage": {}}
    available, reason = _available(request.selection.provider)
    if not available:
        raise HTTPException(status_code=409, detail=reason)
    try:
        if request.selection.provider == "anthropic":
            result, usage = await _anthropic(request)
        elif request.selection.provider == "openai":
            result, usage = await _openai(request)
        elif request.selection.provider == "ollama":
            result, usage = await _ollama(request)
        else:
            result, usage = {"hypotheses": []}, {"latency_ms": 0}
    except (httpx.HTTPError, KeyError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"model call failed: {exc}") from exc
    return {
        "hypotheses": result.get("hypotheses", []),
        "engine": f"{request.selection.provider}:{request.selection.model}",
        "usage": usage,
    }

