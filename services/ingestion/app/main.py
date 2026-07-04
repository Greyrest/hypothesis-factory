"""Ingestion-сервис: приём xlsx-отчёта о хвостах -> структурированный JSON.

POST /api/v1/parse — multipart-загрузка отчёта института.
Парсинг идёт из памяти (BytesIO), временные файлы не создаются.
"""
from __future__ import annotations

import io
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

from .core import parse_workbook

app = FastAPI(
    title="HF Ingestion Service",
    description="Парсинг отчётов института по хвостам (xlsx) в структурированный JSON. "
    "Устойчив к #REF!, пропускам, 1-2 потокам, сводным блокам.",
    version="1.0.0",
)


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "service": "ingestion"}


@app.post("/api/v1/parse")
async def parse(file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "Ожидается файл .xlsx")
    try:
        parsed = parse_workbook(io.BytesIO(await file.read()))
    except Exception as e:
        raise HTTPException(422, f"Не удалось разобрать отчёт: {e}") from e
    # имя фабрики — из имени загруженного файла
    parsed["source_file"] = file.filename
    parsed["plant"] = Path(file.filename).stem.replace("Хвосты", "").replace("_2", "").strip()
    return parsed
