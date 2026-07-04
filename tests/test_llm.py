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


# ------------------------------------ custom: любой OpenAI-совместимый API
class _FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def _openai_answer(content: dict) -> dict:
    import json
    return {"choices": [{"message":
                         {"content": "```json\n" + json.dumps(
                             content, ensure_ascii=False) + "\n```"}}]}


def _custom_provider(mod):
    p = mod.OpenAICompatProvider()
    p.base_url, p.api_key, p.model = "http://fake/v1", "k", "any-model"
    return p


def test_custom_provider_enhance_and_translate(llm, monkeypatch):
    """Свой ключ + любой OpenAI-совместимый бэкенд: единая схема ответа."""
    mod = llm["providers.openai_compat"]
    p = _custom_provider(mod)

    hyp = {"base_id": None, "title": "Т", "hypothesis": "Если …, то …",
           "mechanism": "м", "category": "FLOT", "risks": "один риск",
           "roadmap": ["шаг"], "novelty": "4", "feasibility": 9, "risk": 2,
           "rationale": "r"}
    monkeypatch.setattr(mod.httpx, "post", lambda *a, **kw: _FakeResp(
        _openai_answer({"hypotheses": [hyp, {"мусор": True}]})))
    items = p.enhance({"диагностика": {}})
    assert len(items) == 1, "невалидные items отфильтрованы"
    # нормализация под общую схему: строки/выход за 1..5 -> целые в диапазоне
    assert items[0]["novelty"] == 4 and items[0]["feasibility"] == 5
    assert items[0]["risks"] == ["один риск"]

    monkeypatch.setattr(mod.httpx, "post", lambda *a, **kw: _FakeResp(
        _openai_answer({"translations": ["loss of nickel"]})))
    assert p.translate(["потери никеля"], "en") == ["loss of nickel"]


def test_custom_provider_graceful_degradation(llm, monkeypatch):
    """Не настроен или бэкенд упал -> None, конвейер живёт rule-based."""
    mod = llm["providers.openai_compat"]
    for var in ("LLM_BASE_URL", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert mod.OpenAICompatProvider().enhance({}) is None

    p = _custom_provider(mod)
    def boom(*a, **kw):
        raise OSError("сети нет")
    monkeypatch.setattr(mod.httpx, "post", boom)
    assert p.enhance({"x": 1}) is None
    assert p.translate(["x"], "en") is None


def test_context_includes_user_task(llm):
    ctx = llm["schema"].build_context(
        {**_diagnosis(), "project": {"target_kpi": "снизить потери",
                                     "constraints": ["без CAPEX"]}},
        [_draft()], [], [])
    assert ctx["задача_пользователя"]["целевой_KPI"] == "снизить потери"
    assert "без CAPEX" in ctx["задача_пользователя"]["ограничения"]
