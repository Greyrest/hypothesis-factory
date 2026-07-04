"""Gateway: API-сценарии (моки нижележащих сервисов), граф, экспорт."""
from __future__ import annotations

import io

import pytest
from conftest import make_result
from fastapi.testclient import TestClient


@pytest.fixture()
def client(gw, gen, monkeypatch):
    """TestClient с замоканными вызовами ingestion/generation."""
    result = make_result(gen)
    gw["main"]._results.clear()
    gw["main"]._graph_patch.clear()
    gw["main"]._feedback.clear()

    monkeypatch.setattr(gw["clients"], "parse_xlsx",
                        lambda name, content: {"plant": "Тест"})
    monkeypatch.setattr(gw["clients"], "generate",
                        lambda parsed, use_llm, fb, project=None, weights=None:
                        {**result, "project": project})

    def fake_rerank(hyps, fb, weights=None):
        gen["generator"].rank(hyps, fb, weights)
        return hyps
    monkeypatch.setattr(gw["clients"], "rerank", fake_rerank)

    def fake_analyze(diagnosis, text, title, category, seq):
        return gen["analyze"].analyze_hypothesis(
            diagnosis, __import__("conftest").make_kb(), text,
            title=title, category=category, seq=seq)
    monkeypatch.setattr(gw["clients"], "analyze_hypothesis", fake_analyze)

    return TestClient(gw["main"].app)


def _upload(client, kpi="снизить потери Ni", constraints="без CAPEX"):
    return client.post("/api/v1/reports?use_llm=false",
                       files={"file": ("Хвосты Тест.xlsx", io.BytesIO(b"x"))},
                       data={"target_kpi": kpi, "constraints": constraints})


def test_upload_with_interactive_project(client):
    r = _upload(client)
    assert r.status_code == 200
    body = r.json()
    assert body["project"]["target_kpi"] == "снизить потери Ni"
    assert body["project"]["constraints"] == ["без CAPEX"]
    assert body["hypotheses"]


def test_expert_hypothesis_flow(client):
    _upload(client)
    r = client.post("/api/v1/plants/Тест/hypotheses", json={
        "text": "Если установить контактный чан, то потери снизятся на 10%"})
    assert r.status_code == 200
    card = r.json()
    assert card["status"] == "expert_added"
    assert card["rank"] is not None, "гипотеза встала в общее ранжирование"

    # подтверждение/отклонение (ТЗ 8.4)
    r = client.patch(f"/api/v1/plants/Тест/hypotheses/{card['id']}",
                     json={"status": "confirmed"})
    assert r.json()["status"] == "confirmed"
    # удаление
    assert client.delete(
        f"/api/v1/plants/Тест/hypotheses/{card['id']}").status_code == 200
    assert client.delete(
        f"/api/v1/plants/Тест/hypotheses/{card['id']}").status_code == 404


def test_feedback_reranks(client):
    _upload(client)
    before = client.get("/api/v1/plants/Тест/hypotheses").json()
    cat = before[-1]["categories"][0]
    for _ in range(3):
        client.post("/api/v1/feedback", json={"category": cat, "vote": "up"})
    after = client.get("/api/v1/plants/Тест/hypotheses").json()
    h_after = next(h for h in after if h["categories"][0] == cat)
    assert h_after["scores"]["feedback_adj"] > 0


def test_graph_build_and_expert_edit(client):
    _upload(client)
    g = client.get("/api/v1/plants/Тест/graph").json()
    ids = {n["id"] for n in g["nodes"]}
    assert "kpi" in ids and any(i.startswith("h:") for i in ids)
    # трассировка: находка -> гипотеза -> KPI
    assert any(e["to"] == "kpi" for e in g["edges"])

    node = next(i for i in ids if i.startswith("c:"))
    g2 = client.post("/api/v1/plants/Тест/graph/patch",
                     json={"removed_nodes": [node]}).json()
    assert node not in {n["id"] for n in g2["nodes"]}
    assert all(node not in (e["from"], e["to"]) for e in g2["edges"])

    hyp = next(i for i in ids if i.startswith("h:"))
    find = next(i for i in ids if i.startswith("f:"))
    g3 = client.post("/api/v1/plants/Тест/graph/patch",
                     json={"added_edges": [{"from": hyp, "to": find}]}).json()
    added = [e for e in g3["edges"] if e.get("expert")]
    assert added and added[0]["from"] == hyp

    g4 = client.delete("/api/v1/plants/Тест/graph/patch").json()
    assert node in {n["id"] for n in g4["nodes"]}, "сброс возвращает узлы"


def test_graph_merge_patch_idempotent(gw):
    mp = gw["graph"].merge_patch
    p = mp(None, {"removed_nodes": ["a"], "added_edges": [{"from": "x", "to": "y"}]})
    p = mp(p, {"removed_nodes": ["a"], "added_edges": [{"from": "x", "to": "y"}]})
    assert p["removed_nodes"] == ["a"]
    assert len(p["added_edges"]) == 1
    # добавление ребра снимает его прежнее удаление
    p = mp({"removed_edges": ["x->y"]}, {"added_edges": [{"from": "x", "to": "y"}]})
    assert p["removed_edges"] == []


def test_export_on_the_fly(client, tmp_path):
    _upload(client)
    for fmt, marker in [("json", b'"plant"'), ("csv", "rank;priority".encode()),
                        ("md", "## Гипотезы".encode())]:
        r = client.get(f"/api/v1/plants/Тест/export?fmt={fmt}")
        assert r.status_code == 200
        assert marker in r.content
    # CSV начинается с BOM — Excel корректно откроет кириллицу
    r = client.get("/api/v1/plants/Тест/export?fmt=csv")
    assert r.content.startswith("﻿".encode())
    assert client.get("/api/v1/plants/Тест/export?fmt=exe").status_code == 422


def test_unknown_plant_404(client):
    assert client.get("/api/v1/plants/Нет").status_code == 404
    assert client.get("/api/v1/plants/Нет/graph").status_code == 404
