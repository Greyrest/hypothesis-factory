"""Лексический retrieval по базе знаний (kb приходит от knowledge-сервиса)."""
from __future__ import annotations

import re


def retrieve(kb: dict, query_terms: list[str], kinds=("guide", "rule"), top_k=6) -> list[dict]:
    """Простой лексический retrieval: скоринг по пересечению термов."""
    q = {t.lower() for t in query_terms}
    scored = []
    for ch in kb["chunks"]:
        if ch["kind"] not in kinds:
            continue
        words = set(re.findall(r"[а-яёa-z0-9+-]+", ch["text"].lower()))
        score = len(q & words)
        # сигнальные id правил дают бонус
        if ch["kind"] == "rule" and any(t in ch["text"].lower() for t in q):
            score += 2
        if score:
            scored.append((score, ch))
    scored.sort(key=lambda x: -x[0])
    return [ch for _, ch in scored[:top_k]]
