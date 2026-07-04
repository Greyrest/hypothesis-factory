"""Ingestion: разбор xlsx из памяти, устойчивость к битым данным (ТЗ: надёжность)."""
from __future__ import annotations

import io

import openpyxl
import pytest
from fastapi.testclient import TestClient


def build_xlsx() -> bytes:
    """Синтетический отчёт: поток, таблица классов, блоки форм.
    'Извлекаемый металл' намеренно отсутствует — как #REF! в реальном отчёте."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Итог"
    rows = [
        ["Хвосты породные", 1000, 0.5, 5000, 0.3, 3000],
        ["Класс крупности", "Доля класса, %", "Доля потерь эл.28, %",
         "эл.28, т", "Доля потерь эл.29, %", "эл.29, т"],
        ["+71 мкм", 30, 40, 2000, 30, 900],
        ["-45 +20 мкм", 40, 30, 1500, 40, 1200],
        ["-10", 30, 30, 1500, 30, 900],
        ["Итого", 100, 100, 5000, 100, 3000],
        ["+71 мкм", "Доля потерь эл.28, %", "эл.28, т",
         "Доля потерь эл.29, %", "эл.29, т"],
        ["Раскрытый Pnt/Cp", 10, 200, 10, 90],
        ["Закрытый Pnt/Cp", 80, 1600, 70, 630],
        ["Примесь в пирротине", 10, 200, 20, 180],
        ["-10 мкм", "Доля потерь эл.28, %", "эл.28, т",
         "Доля потерь эл.29, %", "эл.29, т"],
        ["Раскрытый Pnt/Cp", 80, 1200, 80, 720],
        ["Примесь в пирротине", 20, 300, 20, 180],
    ]
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_from_memory(ing):
    parsed = ing["core"].parse_workbook(io.BytesIO(build_xlsx()))
    assert len(parsed["streams"]) == 1
    stream = parsed["streams"][0]
    assert stream["ni_t"] == 5000
    classes = {c["cls"]: c for c in stream["size_classes"]}
    assert set(classes) == {"+71", "-45+20", "-10"}
    assert classes["+71"]["forms"]["Закрытый Pnt/Cp"]["ni_t"] == 1600


def test_recoverable_restored_from_forms(ing):
    """#REF!/пропуск в «Извлекаемый металл» -> восстановление из форм + warning."""
    parsed = ing["core"].parse_workbook(io.BytesIO(build_xlsx()))
    entry = next(c for c in parsed["streams"][0]["size_classes"]
                 if c["cls"] == "+71")
    # раскрытый 200 + закрытый 1600 (примесь не извлекается)
    assert entry["recoverable"]["ni_t"] == 1800
    assert entry["recoverable"].get("estimated") is True
    assert any("восстановлен из форм" in w for w in parsed["warnings"])


def test_canon_helpers(ing):
    core = ing["core"]
    assert core.canon_class(" -20 + 10 мкм") == "-20+10"
    assert core.canon_class("+125") == "+125"
    assert core.canon_class("не класс") is None
    assert core.canon_form("Раскрытый Pnt/Cp") == "Раскрытый Pnt/Cp"
    assert core.canon_form("закрытый (в сростках)") == "Закрытый Pnt/Cp"


def test_api_parse_and_validation(ing):
    client = TestClient(ing["main"].app)
    r = client.post("/api/v1/parse",
                    files={"file": ("Хвосты Тест.xlsx", build_xlsx())})
    assert r.status_code == 200
    assert r.json()["plant"] == "Тест"

    r = client.post("/api/v1/parse", files={"file": ("evil.txt", b"123")})
    assert r.status_code == 400

    r = client.post("/api/v1/parse",
                    files={"file": ("broken.xlsx", b"not an xlsx")})
    assert r.status_code == 422  # битый файл не роняет сервис
