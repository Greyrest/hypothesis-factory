"""HTTP-клиенты нижележащих сервисов."""
from __future__ import annotations

import os

import httpx

INGESTION_URL = os.environ.get("INGESTION_URL", "http://localhost:8001")
KNOWLEDGE_URL = os.environ.get("KNOWLEDGE_URL", "http://localhost:8002")
GENERATION_URL = os.environ.get("GENERATION_URL", "http://localhost:8003")
LLM_URL = os.environ.get("LLM_URL", "http://localhost:8004")

TIMEOUT = httpx.Timeout(300.0, connect=10.0)


def parse_xlsx(filename: str, content: bytes) -> dict:
    r = httpx.post(f"{INGESTION_URL}/api/v1/parse",
                   files={"file": (filename, content,
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def generate(parsed: dict, use_llm: bool, feedback: dict | None) -> dict:
    r = httpx.post(f"{GENERATION_URL}/api/v1/generate",
                   json={"parsed": parsed, "use_llm": use_llm, "feedback": feedback},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def rerank(hypotheses: list[dict], feedback: dict | None) -> list[dict]:
    r = httpx.post(f"{GENERATION_URL}/api/v1/rerank",
                   json={"hypotheses": hypotheses, "feedback": feedback},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def services_health() -> dict:
    out = {}
    for name, url in [("ingestion", INGESTION_URL), ("knowledge", KNOWLEDGE_URL),
                      ("generation", GENERATION_URL), ("llm", LLM_URL)]:
        try:
            r = httpx.get(f"{url}/api/v1/health", timeout=5.0)
            out[name] = r.json()
        except Exception as e:
            out[name] = {"status": "down", "error": str(e)}
    return out
