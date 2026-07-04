"""Общие фикстуры: загрузка сервисов по путям + синтетические данные.

Каждый сервис — самостоятельный пакет `app`, поэтому загружаем их по очереди,
снимая снапшот модулей (ссылки остаются живыми после очистки sys.modules).
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_loaded: dict[str, dict] = {}


def load_service(name: str, env: dict | None = None,
                 extra: tuple[str, ...] = ()) -> dict:
    """Импортирует services/<name>/app и возвращает {подмодуль: модуль}."""
    if name in _loaded:
        return _loaded[name]
    for k, v in (env or {}).items():
        os.environ[k] = v
    svc = str(ROOT / "services" / name)
    for m in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    sys.path.insert(0, svc)
    try:
        importlib.import_module("app.main")
        for sub in extra:  # модули с ленивым импортом (провайдеры)
            importlib.import_module(f"app.{sub}")
        mods = {(k.split(".", 1)[1] if "." in k else "_pkg"): v
                for k, v in sys.modules.items()
                if k == "app" or k.startswith("app.")}
    finally:
        sys.path.remove(svc)
    _loaded[name] = mods
    return mods


@pytest.fixture(scope="session")
def ing():
    return load_service("ingestion")


@pytest.fixture(scope="session")
def gen():
    return load_service("generation")


@pytest.fixture(scope="session")
def llm():
    return load_service("llm", {"LLM_PROVIDER": "mock"},
                        extra=("providers.anthropic_provider",))


@pytest.fixture(scope="session")
def kn():
    return load_service("knowledge", {"DATA_DIR": "/nonexistent-hf-data"})


@pytest.fixture(scope="session")
def gw():
    return load_service("gateway", {"HF_PERSIST": "0",
                                    "DATA_DIR": "/nonexistent-hf-data"})


# ------------------------------------------------------- синтетические данные
def make_components() -> list[dict]:
    return [
        {"id": "ni", "num": 28, "label": "Элемент 28 (Ni)", "unit": "т",
         "recoverable_forms": ["Закрытый Pnt/Cp", "Миллерит", "Раскрытый Pnt/Cp"]},
        {"id": "cu", "num": 29, "label": "Элемент 29 (Cu)", "unit": "т",
         "recoverable_forms": ["Закрытый Pnt/Cp", "Раскрытый Pnt/Cp"]},
    ]


def make_parsed() -> dict:
    """Разобранный отчёт: 1 поток, 3 класса, формы с закрытым/раскрытым Ni."""
    def cls(name, share, locked, liberated, impurity):
        forms = {}
        if locked:
            forms["Закрытый Pnt/Cp"] = {"ni_t": locked, "cu_t": 0}
        if liberated:
            forms["Раскрытый Pnt/Cp"] = {"ni_t": liberated, "cu_t": 0}
        if impurity:
            forms["Примесь в пирротине"] = {"ni_t": impurity, "cu_t": 0}
        return {"cls": name, "share_pct": share,
                "ni_t": locked + liberated + impurity, "cu_t": 0,
                "forms": forms,
                "recoverable": {"ni_t": locked + liberated, "cu_t": 0}}

    classes = [
        cls("+71", 30, 1600, 200, 200),      # недоизмельчение + проскок
        cls("-45+20", 40, 400, 800, 300),    # недофлотация + сростки
        cls("-10", 30, 0, 1200, 300),        # шламовые потери
    ]
    rec = sum(c["recoverable"]["ni_t"] for c in classes)
    tot = sum(c["ni_t"] for c in classes)
    return {
        "source_file": "Хвосты Тест.xlsx",
        "plant": "Тест",
        "components": make_components(),
        "feed": {}, "tailings_fact": None, "warnings": [],
        "streams": [{
            "name": "Хвосты породные", "smt": 1000,
            "ni_pct": 0.5, "ni_t": tot, "cu_pct": 0.0, "cu_t": 0,
            "aggregate": False,
            "size_classes": classes,
            "totals": {"ni_t": tot, "cu_t": 0,
                       "recoverable_ni_t": rec, "recoverable_cu_t": 0},
        }],
    }


def make_parsed_custom(cid: str = "el27", label: str = "Элемент 27") -> dict:
    """Отчёт с одним произвольным компонентом — конвейер не знает ni/cu."""
    def cls_(name, share, locked, liberated):
        forms = {}
        if locked:
            forms["Закрытый Pnt/Cp"] = {f"{cid}_t": locked}
        if liberated:
            forms["Раскрытый Pnt/Cp"] = {f"{cid}_t": liberated}
        return {"cls": name, "share_pct": share, f"{cid}_t": locked + liberated,
                "forms": forms, "recoverable": {f"{cid}_t": locked + liberated}}

    classes = [cls_("+71", 30, 1600, 200), cls_("-45+20", 40, 400, 800),
               cls_("-10", 30, 0, 1200)]
    tot = sum(c[f"{cid}_t"] for c in classes)
    return {
        "source_file": "Хвосты Тест2.xlsx", "plant": "Тест2",
        "components": [{"id": cid, "num": 27, "label": label, "unit": "т",
                        "recoverable_forms": ["Закрытый Pnt/Cp",
                                              "Раскрытый Pnt/Cp"]}],
        "feed": {}, "tailings_fact": None, "warnings": [],
        "streams": [{
            "name": "Хвосты породные", "smt": 1000,
            f"{cid}_pct": 0.5, f"{cid}_t": tot,
            "aggregate": False, "size_classes": classes,
            "totals": {f"{cid}_t": tot, f"recoverable_{cid}_t": tot},
        }],
    }


def make_kb() -> dict:
    rules = [
        dict(id="R1", signal="coarse_locked",
             title="Закрытый металл в крупных классах",
             text="Металл в сростках не раскрыт: нужно измельчение и классификация.",
             categories=["GRIND", "CLASSIFY"], source="Справка института"),
        dict(id="R2", signal="fine_liberated",
             title="Шламовые потери",
             text="Раскрытый минерал в тоне -10 мкм теряется флотацией: реагентный режим.",
             categories=["REAGENT"], source="Абрамов А.А."),
    ]
    chunks = [{"id": r["id"], "kind": "rule", "source": r["source"],
               "text": f"{r['title']}. {r['text']}"} for r in rules]
    catalog = [
        dict(id="cat-01", title="Замена футеровки мельниц",
             source="Мозговой штурм, Пример 1", plants=["X"],
             categories=["GRIND"], signals=["coarse_locked"],
             equipment="мельницы", feasibility=4, risk=2, novelty=2,
             capex="низкий"),
        dict(id="cat-02", title="Замена песковых насадок на гидроциклонах",
             source="Мозговой штурм, Пример 2", plants=["Y"],
             categories=["CLASSIFY"], signals=["coarse_locked", "coarse_share"],
             equipment="гидроциклоны", feasibility=4, risk=2, novelty=2,
             capex="низкий"),
        dict(id="cat-03", title="Подбор реагента для шламов",
             source="Мозговой штурм, Пример 3", plants=["Z"],
             categories=["REAGENT"], signals=["fine_liberated"],
             equipment="реагентное хозяйство", feasibility=4, risk=3, novelty=4,
             capex="низкий"),
    ]
    return {"chunks": chunks, "catalog": catalog, "rules": rules}


def make_result(gen_mods) -> dict:
    """Готовый результат конвейера на синтетике (для gateway-тестов)."""
    diagnosis = gen_mods["diagnosis"].diagnose(make_parsed())
    return gen_mods["generator"].generate(diagnosis, make_kb(), use_llm=False)
