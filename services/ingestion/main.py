from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from services.common.config import DATA_DIR
from services.common.health import health
from services.common.models import FileRef, IngestionRequest

app = FastAPI(
    title="Hypothesis Factory · Ingestion Service",
    version="2.0.0",
    description="Normalizes uploaded reports and documents into facts and domain diagnostics.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


def _safe_path(file: FileRef) -> Path:
    path = Path(file.path).resolve()
    if DATA_DIR not in path.parents and path != DATA_DIR:
        raise HTTPException(status_code=400, detail=f"file is outside shared data directory: {file.filename}")
    if not path.is_file():
        raise HTTPException(status_code=422, detail=f"file not found: {file.filename}")
    return path


def _text_facts(file: FileRef, path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    facts: list[dict[str, Any]] = []
    try:
        if suffix in {".txt", ".md"}:
            chunks = [p.strip() for p in path.read_text("utf-8", errors="replace").split("\n\n")]
            facts = [{"kind": "text", "text": text} for text in chunks if text]
        elif suffix == ".json":
            facts = [{"kind": "json", "data": json.loads(path.read_text("utf-8"))}]
        elif suffix == ".csv":
            raw = path.read_text("utf-8-sig", errors="replace")
            delimiter = ";" if raw.count(";") > raw.count(",") else ","
            facts = [{"kind": "row", "data": row} for row in csv.DictReader(raw.splitlines(), delimiter=delimiter)]
        elif suffix == ".docx":
            from docx import Document

            facts = [
                {"kind": "text", "text": p.text.strip()}
                for p in Document(path).paragraphs
                if p.text.strip()
            ]
        elif suffix == ".pdf":
            from pypdf import PdfReader

            facts = [
                {"kind": "text", "text": page.extract_text().strip(), "page": index + 1}
                for index, page in enumerate(PdfReader(str(path)).pages)
                if page.extract_text() and page.extract_text().strip()
            ]
    except Exception as exc:
        facts = [{"kind": "parse_error", "text": str(exc)}]
    for index, fact in enumerate(facts):
        fact.update({"id": f"{file.id}:{index}", "source_id": file.id, "filename": file.filename})
    return facts


@app.get("/api/v1/health", tags=["System"], summary="Service health")
def service_health() -> dict:
    return health("ingestion")


@app.post("/api/v1/ingestions", tags=["Ingestion"], summary="Parse project inputs")
def ingest(request: IngestionRequest) -> dict:
    paths = [(file, _safe_path(file)) for file in request.files]
    facts = [fact for file, path in paths for fact in _text_facts(file, path)]
    warnings: list[str] = []

    if request.domain == "mining_flotation":
        report = next((path for _file, path in paths if path.suffix.lower() == ".xlsx"), None)
        if report is None:
            raise HTTPException(
                status_code=422,
                detail="mining_flotation requires at least one XLSX tailings report",
            )
        try:
            from parse_tailings import parse_workbook
            from diagnose import diagnose

            parsed = parse_workbook(report)
            diagnosis = diagnose(parsed)
            warnings.extend(parsed.get("warnings", []))
            facts.append({
                "id": f"{request.project_id}:report",
                "kind": "parsed_report",
                "source_id": next(file.id for file, path in paths if path == report),
                "data": {
                    "plant": parsed.get("plant"),
                    "feed": parsed.get("feed"),
                    "tailings_fact": parsed.get("tailings_fact"),
                },
            })
            return {
                "project_id": request.project_id,
                "domain": request.domain,
                "facts": facts,
                "diagnosis": diagnosis,
                "summary": diagnosis.get("summary", {}),
                "warnings": warnings,
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"cannot parse flotation report: {exc}") from exc

    return {
        "project_id": request.project_id,
        "domain": request.domain,
        "facts": facts,
        "diagnosis": {"plant": request.project_id, "findings": [], "cells": [], "summary": {}},
        "summary": {"facts": len(facts)},
        "warnings": warnings,
    }

