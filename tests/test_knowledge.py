"""Knowledge: retrieval с цитированием, метаданные каталога."""
from __future__ import annotations

from conftest import make_kb
from fastapi.testclient import TestClient


def test_retrieve_finds_relevant_rule(kn):
    kb = make_kb()
    found = kn["core"].retrieve(kb, ["измельчение", "сростках", "закрытый"],
                                kinds=("rule",), top_k=2)
    assert found and found[0]["id"] == "R1"
    assert found[0]["source"], "каждый чанк несёт источник для цитирования"


def test_retrieve_empty_for_garbage(kn):
    assert kn["core"].retrieve(make_kb(), ["квазар"], top_k=3) == []


def test_catalog_meta_matching(kn):
    meta = kn["core"]._catalog_meta("Замена футеровки шаровых мельниц")
    assert meta["categories"] == ["GRIND"]
    meta = kn["core"]._catalog_meta("Замена песковых насадок на гидроциклонах")
    assert "CLASSIFY" in meta["categories"]
    # неизвестная практика получает дефолтные метаданные, а не падает
    meta = kn["core"]._catalog_meta("Совершенно новая практика")
    assert {"categories", "signals", "feasibility", "risk", "novelty"} <= set(meta)


def test_domain_rules_cite_literature(kn):
    for rule in kn["core"].DOMAIN_RULES:
        assert rule["source"], f"правило {rule['id']} без источника"
        assert rule["categories"], f"правило {rule['id']} без категорий решений"


def test_api_health_and_empty_kb(kn):
    client = TestClient(kn["main"].app)
    data = client.get("/api/v1/health").json()
    assert data["status"] == "ok"
    # DATA_DIR не существует -> rebuild отвечает 404, а не 500
    assert client.post("/api/v1/kb/rebuild").status_code == 404
