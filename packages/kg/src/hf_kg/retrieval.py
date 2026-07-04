"""Лексический retrieval по чанкам базы знаний.

Чанк: {"id", "kind", "source", "text"}. Скоринг — пересечение термов запроса
со словами чанка; чанкам-правилам даётся бонус за прямое вхождение терма
(поведение прототипа сохранено).
"""
from __future__ import annotations

import re


def retrieve(chunks: list[dict], query_terms: list[str],
             kinds: tuple[str, ...] | None = ("guide", "rule"),
             top_k: int = 6) -> list[dict]:
    q = {t.lower() for t in query_terms}
    scored = []
    for ch in chunks:
        if kinds is not None and ch["kind"] not in kinds:
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
