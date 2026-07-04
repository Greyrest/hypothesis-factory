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


def generate(parsed: dict, use_llm: bool, feedback: dict | None,
             project: dict | None = None,
             weights: dict | None = None) -> dict:
    r = httpx.post(f"{GENERATION_URL}/api/v1/generate",
                   json={"parsed": parsed, "use_llm": use_llm,
                         "feedback": feedback, "project": project,
                         "weights": weights},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def analyze_hypothesis(diagnosis: dict, text: str, title: str | None,
                       category: str | None, seq: int) -> dict:
    r = httpx.post(f"{GENERATION_URL}/api/v1/analyze",
                   json={"diagnosis": diagnosis, "text": text, "title": title,
                         "category": category, "seq": seq},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def rerank(hypotheses: list[dict], feedback: dict | None,
           weights: dict | None = None) -> list[dict]:
    r = httpx.post(f"{GENERATION_URL}/api/v1/rerank",
                   json={"hypotheses": hypotheses, "feedback": feedback,
                         "weights": weights},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def whatif(diagnosis: dict, signal: str, reduction_pct: float) -> dict:
    r = httpx.post(f"{GENERATION_URL}/api/v1/whatif",
                   json={"diagnosis": diagnosis, "signal": signal,
                         "reduction_pct": reduction_pct},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def llm_translate(texts: list[str], lang: str) -> list[str] | None:
    r = httpx.post(f"{LLM_URL}/api/v1/translate",
                   json={"texts": texts, "lang": lang}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["translations"]


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
