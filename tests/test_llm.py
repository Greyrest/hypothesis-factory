"""LLM-сервис: сменные провайдеры, единая схема, устойчивость без сети (ТЗ)."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _draft():
    return {"id": "Тест-cat-01", "title": "Гипотеза", "categories": ["GRIND"],
            "expected_effect": {"addressable_t": {"ni": 100, "cu": 0}},
            "evidence": [{"source": "s", "fact": "f"}]}


def _diagnosis():
    return {"plant": "Тест", "summary": {}, "findings": []}


def test_health_shows_provider(llm):
    client = TestClient(llm["main"].app)
    data = client.get("/api/v1/health").json()
    assert data["provider"] == "mock"


def test_enhance_mock_returns_items(llm):
    client = TestClient(llm["main"].app)
    r = client.post("/api/v1/enhance", json={
        "diagnosis": _diagnosis(), "drafts": [_draft()],
        "catalog": [], "rules": []})
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and items[0]["base_id"] == "Тест-cat-01"
    # ответ соответствует общей схеме независимо от модели
    for key in ("title", "hypothesis", "mechanism", "category",
                "novelty", "feasibility", "risk", "rationale"):
        assert key in items[0]


def test_null_provider_graceful(llm):
    """LLM отключён/недоступен -> None, конвейер не падает (rule-based)."""
    provider = llm["providers.base"].NullProvider()
    assert provider.enhance({}) is None


def test_anthropic_no_key_returns_none(llm, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from_mod = llm["providers.anthropic_provider"]
    assert from_mod.AnthropicProvider().enhance({}) is None


def test_context_includes_user_task(llm):
    ctx = llm["schema"].build_context(
        {**_diagnosis(), "project": {"target_kpi": "снизить потери",
                                     "constraints": ["без CAPEX"]}},
        [_draft()], [], [])
    assert ctx["задача_пользователя"]["целевой_KPI"] == "снизить потери"
    assert "без CAPEX" in ctx["задача_пользователя"]["ограничения"]
