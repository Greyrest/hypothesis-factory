"""HTTP-клиент llm-сервиса. Недоступность LLM — штатный режим (rule-based)."""
from __future__ import annotations

import os

import httpx

LLM_URL = os.environ.get("LLM_URL", "http://localhost:8004")


def llm_enhance_remote(diagnosis: dict, drafts: list[dict],
                       kb: dict) -> tuple[list[dict] | None, str]:
    """-> (items | None, подпись модели). None => остаёмся на rule-based."""
    try:
        diag = {k: diagnosis[k] for k in ("plant", "summary", "findings")}
        if diagnosis.get("project"):
            diag["project"] = diagnosis["project"]
        r = httpx.post(f"{LLM_URL}/api/v1/enhance", json={
            "diagnosis": diag,
            "drafts": drafts,
            "catalog": kb.get("catalog", []),
            "rules": kb.get("rules", []),
        }, timeout=180.0)
        r.raise_for_status()
        data = r.json()
        label = f"{data.get('provider', '?')}:{data.get('model', '?')}"
        return data.get("items"), label
    except Exception as e:
        print(f"[llm-client] пропущено: {type(e).__name__}: {e}")
        return None, ""
