"""Knowledge-сервис: база знаний (справка, каталог практик, правила) + retrieval.

База строится при старте из DATA_DIR (справка docx, эталонные гипотезы docx,
литература pdf) и может быть перестроена через POST /api/v1/kb/rebuild.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .core import build_kb, retrieve

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

app = FastAPI(
    title="HF Knowledge Service",
    description="База знаний для генерации гипотез: чанки справки с цитированием, "
    "каталог практик из мозговых штурмов 4 фабрик, правила физики обогащения "
    "с привязкой к литературе; лексический retrieval.",
    version="1.0.0",
)

_kb: dict = {"chunks": [], "catalog": [], "rules": []}


class RetrieveRequest(BaseModel):
    query_terms: list[str]
    kinds: list[str] = ["guide", "rule"]
    top_k: int = 6


@app.on_event("startup")
def _startup():
    global _kb
    if DATA_DIR.exists():
        _kb = build_kb(DATA_DIR)


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "service": "knowledge",
            "kb": {"chunks": len(_kb["chunks"]), "catalog": len(_kb["catalog"]),
                   "rules": len(_kb["rules"])}}


@app.get("/api/v1/kb")
def get_kb() -> dict:
    """Полная база знаний (для генератора)."""
    return _kb


@app.post("/api/v1/kb/rebuild")
def rebuild() -> dict:
    global _kb
    if not DATA_DIR.exists():
        raise HTTPException(404, f"DATA_DIR не найден: {DATA_DIR}")
    _kb = build_kb(DATA_DIR)
    return {"chunks": len(_kb["chunks"]), "catalog": len(_kb["catalog"]),
            "rules": len(_kb["rules"])}


@app.post("/api/v1/retrieve")
def retrieve_chunks(req: RetrieveRequest) -> list[dict]:
    return retrieve(_kb, req.query_terms, kinds=tuple(req.kinds), top_k=req.top_k)
