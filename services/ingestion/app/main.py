"""Ingestion-сервис: приём xlsx-отчёта о хвостах -> структурированный JSON.

POST /api/v1/parse — multipart-загрузка отчёта института.
"""
from __future__ import annotations

import tempfile
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
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        parsed = parse_workbook(tmp_path)
    except Exception as e:
        raise HTTPException(422, f"Не удалось разобрать отчёт: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)
    # имя фабрики берём из имени загруженного файла, а не временного
    parsed["source_file"] = file.filename
    parsed["plant"] = Path(file.filename).stem.replace("Хвосты", "").replace("_2", "").strip()
    return parsed
