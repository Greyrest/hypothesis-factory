from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from services.common.config import DATA_DIR
from services.gateway import main as gateway_module
from services.gateway.store import Store
from services.hypothesis.main import app as hypothesis_app
from services.ingestion.main import app as ingestion_app
from services.knowledge.main import app as knowledge_app
from services.model_runtime.main import app as model_app


class ServiceContractTests(unittest.TestCase):
    @staticmethod
    def _tailings_report(path: Path) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Итог"
        rows = [
            ["Хвосты породные", 10000, 0.01, 100, 0.005, 50],
            ["Класс крупности", "Доля класса", "Доля потерь 28", "28, т", "Доля потерь 29", "29, т"],
            ["+125", 40, 80, 80, 80, 40],
            ["+125 мкм", "Доля класса", "Доля потерь 28", "28, т", "Доля потерь 29", "29, т"],
            ["Закрытый Pnt/Cp", None, 80, 80, 80, 40],
            ["Раскрытый Pnt/Cp", None, 20, 20, 20, 10],
        ]
        for row in rows:
            sheet.append(row)
        workbook.save(path)

    def test_every_service_exposes_openapi_and_health(self):
        for app in (ingestion_app, knowledge_app, hypothesis_app, model_app):
            with self.subTest(app=app.title), TestClient(app) as client:
                self.assertEqual(client.get("/api/v1/health").status_code, 200)
                schema = client.get("/openapi.json").json()
                self.assertEqual(schema["openapi"][:3], "3.1")
                self.assertTrue(schema["paths"])

    def test_generic_pipeline_components(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        source = DATA_DIR / "contract-test.txt"
        source.write_text("Изменение температуры влияет на прочность образца.", encoding="utf-8")
        file_ref = {"id": "file-1", "filename": source.name, "path": str(source), "kind": "data"}

        with TestClient(ingestion_app) as client:
            ingestion = client.post("/api/v1/ingestions", json={
                "project_id": "p-1", "domain": "generic", "files": [file_ref],
            }).json()
        self.assertGreaterEqual(len(ingestion["facts"]), 1)

        with TestClient(knowledge_app) as client:
            knowledge = client.post("/api/v1/context", json={
                "project_id": "p-1", "domain": "generic", "files": [file_ref], "ingestion": ingestion,
            }).json()
        with TestClient(hypothesis_app) as client:
            result = client.post("/api/v1/generations", json={
                "project_id": "p-1",
                "domain": "generic",
                "target_kpi": "Повысить прочность",
                "constraints": [],
                "ingestion": ingestion,
                "knowledge": knowledge,
                "model": {"provider": "mock", "model": "deterministic", "enabled": False},
                "feedback": {},
            }).json()
        self.assertGreaterEqual(len(result["hypotheses"]), 1)

        with TestClient(knowledge_app) as client:
            graph = client.post("/api/v1/graphs", json={
                "project": {"id": "p-1", "target_kpi": "Повысить прочность"},
                "ingestion": ingestion,
                "hypotheses": result["hypotheses"],
            }).json()
        self.assertTrue(any(node["group"] == "hypothesis" for node in graph["nodes"]))

    def test_mining_flotation_xlsx_pipeline(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        source = DATA_DIR / "Хвосты Тест.xlsx"
        self._tailings_report(source)
        file_ref = {"id": "xlsx-1", "filename": source.name, "path": str(source), "kind": "report"}

        with TestClient(ingestion_app) as client:
            response = client.post("/api/v1/ingestions", json={
                "project_id": "mining-1", "domain": "mining_flotation", "files": [file_ref],
            })
            self.assertEqual(response.status_code, 200, response.text)
            ingestion = response.json()
        self.assertTrue(any(item["signal"] == "coarse_locked" for item in ingestion["diagnosis"]["findings"]))

        with TestClient(knowledge_app) as client:
            knowledge = client.post("/api/v1/context", json={
                "project_id": "mining-1", "domain": "mining_flotation", "files": [file_ref], "ingestion": ingestion,
            }).json()
        with TestClient(hypothesis_app) as client:
            response = client.post("/api/v1/generations", json={
                "project_id": "mining-1",
                "domain": "mining_flotation",
                "target_kpi": "Снизить потери Ni/Cu",
                "constraints": [],
                "ingestion": ingestion,
                "knowledge": knowledge,
                "model": {"provider": "mock", "model": "deterministic", "enabled": False},
                "feedback": {},
            })
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
        self.assertGreaterEqual(len(result["hypotheses"]), 2)
        self.assertGreater(result["hypotheses"][0]["scores"]["impact_t"], 0)

    def test_gateway_project_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            gateway_module.store = Store(Path(directory) / "api.sqlite3")
            with TestClient(gateway_module.app) as client:
                response = client.post("/api/v1/projects", json={
                    "domain": "generic",
                    "title": "Материаловедческий тест",
                    "target_kpi": "Повысить прочность на 10%",
                    "constraints": ["Температура до 800 C"],
                })
                self.assertEqual(response.status_code, 201)
                project = response.json()
                self.assertEqual(client.get(f"/api/v1/projects/{project['id']}").status_code, 200)
                self.assertEqual(client.get("/api/v1/projects").json()["items"][0]["id"], project["id"])


if __name__ == "__main__":
    unittest.main()
