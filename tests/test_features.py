"""Тесты добавленных характеристик ТЗ: веса, валидация, what-if,
DOCX-экспорт, перевод, авторизация."""
from __future__ import annotations

import io

from conftest import make_kb, make_parsed
from fastapi.testclient import TestClient


# --------------------------------------------------- веса и валидация (rank)
def _card(i, cat, impact, feas=3, nov=3, status="catalog"):
    return {"id": f"h{i}", "categories": [cat], "status": status,
            "scores": {"feasibility": feas, "novelty": nov, "risk": 3,
                       "impact_t": impact}}


def test_custom_weights_change_order(gen):
    rank = gen["generator"].rank
    hyps = [_card(1, "GRIND", 100, feas=1), _card(2, "FLOT", 10, feas=5)]
    rank(hyps)  # дефолт: эффект решает
    assert hyps[0]["id"] == "h1"
    rank(hyps, weights={"impact": 0, "feasibility": 1, "risk": 0, "novelty": 0})
    assert hyps[0]["id"] == "h2", "при весе только на реализуемость порядок меняется"


def test_validation_status_affects_rank(gen):
    rank = gen["generator"].rank
    hyps = [_card(1, "GRIND", 100), _card(2, "FLOT", 100, status="rejected"),
            _card(3, "TAILS", 100, status="confirmed")]
    rank(hyps)
    assert hyps[0]["id"] == "h3", "подтверждённая — выше"
    assert hyps[-1]["id"] == "h2", "отклонённая — вниз списка"


# ------------------------------------------------------------------ what-if
def test_whatif_counterfactual(gen):
    client = TestClient(gen["main"].app)
    d = gen["diagnosis"].diagnose(make_parsed())
    r = client.post("/api/v1/whatif", json={
        "diagnosis": d, "signal": "coarse_locked", "reduction_pct": 50})
    assert r.status_code == 200
    body = r.json()
    # закрытый Ni в крупных классах = 1600 т; 50% = 800 т
    assert body["addressable_t"]["ni"] == 1600
    assert body["kpi_delta_t"]["ni"] == 800
    assert body["losses_after_t"]["ni"] == d["summary"]["losses_ni_t"] - 800

    r = client.post("/api/v1/whatif", json={
        "diagnosis": d, "signal": "нет_такого", "reduction_pct": 50})
    assert r.status_code == 400


# --------------------------------------------------------- перевод (LLM-слой)
def test_translate_mock_and_null(llm):
    client = TestClient(llm["main"].app)
    r = client.post("/api/v1/translate",
                    json={"texts": ["потери никеля"], "lang": "en"})
    assert r.json()["translations"] == ["[en] потери никеля"]
    # null-провайдер честно возвращает недоступность
    provider = llm["providers.base"].NullProvider()
    assert provider.translate(["x"], "en") is None


# ------------------------------------------------------- gateway: docx, веса
def _upload(client):
    return client.post("/api/v1/reports?use_llm=false",
                       files={"file": ("Хвосты Тест.xlsx", io.BytesIO(b"x"))},
                       data={"target_kpi": "", "constraints": ""})


def make_client(gw, gen, monkeypatch):
    from conftest import make_result
    result = make_result(gen)
    gw["main"]._results.clear()
    gw["main"]._weights.clear()
    monkeypatch.setattr(gw["clients"], "parse_xlsx",
                        lambda name, content: {"plant": "Тест"})
    monkeypatch.setattr(gw["clients"], "generate",
                        lambda parsed, use_llm, fb, project=None, weights=None:
                        dict(result))

    def fake_rerank(hyps, fb, weights=None):
        gen["generator"].rank(hyps, fb, weights)
        return hyps
    monkeypatch.setattr(gw["clients"], "rerank", fake_rerank)
    monkeypatch.setattr(gw["clients"], "whatif",
                        lambda d, s, p: {"signal": s, "reduction_pct": p,
                                         "addressable_t": {"ni": 1, "cu": 0},
                                         "kpi_delta_t": {"ni": 1, "cu": 0},
                                         "losses_after_t": {"ni": 1, "cu": 0}})
    return TestClient(gw["main"].app)


def test_gateway_weights_endpoint(gw, gen, monkeypatch):
    client = make_client(gw, gen, monkeypatch)
    _upload(client)
    assert client.get("/api/v1/weights").json()["impact"] == 0.40
    r = client.put("/api/v1/weights", json={
        "impact": 0.1, "feasibility": 0.7, "risk": 0.1, "novelty": 0.1})
    assert r.status_code == 200
    assert client.get("/api/v1/weights").json()["feasibility"] == 0.7
    # некорректные веса отклоняются
    assert client.put("/api/v1/weights", json={
        "impact": -1, "feasibility": 0, "risk": 0, "novelty": 0}).status_code \
        in (400, 422)


def test_gateway_docx_export(gw, gen, monkeypatch):
    client = make_client(gw, gen, monkeypatch)
    _upload(client)
    r = client.get("/api/v1/plants/Тест/export?fmt=docx")
    assert r.status_code == 200
    assert r.content[:2] == b"PK", "docx — это zip-контейнер"
    assert "wordprocessingml" in r.headers["content-type"]


def test_gateway_whatif_route(gw, gen, monkeypatch):
    client = make_client(gw, gen, monkeypatch)
    _upload(client)
    r = client.get("/api/v1/plants/Тест/whatif?signal=coarse_locked&reduction_pct=30")
    assert r.status_code == 200
    assert r.json()["signal"] == "coarse_locked"


def test_api_key_auth(gw, gen, monkeypatch):
    client = make_client(gw, gen, monkeypatch)
    monkeypatch.setattr(gw["main"], "API_KEY", "secret")
    assert client.get("/api/v1/plants").status_code == 401
    assert client.get("/api/v1/health").status_code == 200, "health открыт"
    assert client.get("/api/v1/plants",
                      headers={"X-API-Key": "secret"}).status_code == 200
