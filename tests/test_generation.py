"""Generation: диагностика, генерация, ранжирование, произвольные гипотезы."""
from __future__ import annotations

from conftest import make_kb, make_parsed


def test_diagnose_signals(gen):
    d = gen["diagnosis"].diagnose(make_parsed())
    signals = {f["signal"] for f in d["findings"] if not f.get("informational")}
    assert {"coarse_locked", "fine_liberated", "mid_liberated",
            "coarse_share"} <= signals
    # неизвлекаемая примесь — только справочно, гипотез не порождает
    info = [f for f in d["findings"] if f.get("informational")]
    assert all(f["signal"] == "pyrrhotite_info" for f in info)
    # findings отсортированы по убыванию тонн
    tons = [f["tons"] for f in d["findings"]]
    assert tons == sorted(tons, reverse=True)


def test_rule_based_cards_complete(gen):
    d = gen["diagnosis"].diagnose(make_parsed())
    hyps = gen["generator"].rule_based_generate(d, make_kb())
    assert hyps, "каталог должен породить гипотезы"
    for h in hyps:
        # обязательные поля карточки по ТЗ: обоснование, механизм, KPI,
        # риски, дорожная карта, источники, трассировка
        assert h["evidence"] and h["mechanism"] and h["roadmap"] and h["risks"]
        assert h["sources"] and h["finding_ids"]
        assert h["expected_effect"]["kpi_delta_t"]["ni"][0] <= \
               h["expected_effect"]["kpi_delta_t"]["ni"][1]


def test_physical_control(gen):
    """Адресуемый металл гипотезы не превышает фактические потери отчёта."""
    parsed = make_parsed()
    total_ni = parsed["streams"][0]["totals"]["ni_t"]
    d = gen["diagnosis"].diagnose(parsed)
    for h in gen["generator"].rule_based_generate(d, make_kb()):
        assert h["expected_effect"]["addressable_t"]["ni"] <= total_ni


def test_rank_feedback_and_diversity(gen):
    rank = gen["generator"].rank

    def card(i, cat, impact):
        return {"id": f"h{i}", "categories": [cat],
                "scores": {"feasibility": 3, "novelty": 3, "risk": 3,
                           "impact_t": impact}}

    hyps = [card(1, "GRIND", 100), card(2, "GRIND", 100), card(3, "FLOT", 100)]
    rank(hyps)
    # штраф за однотипность: вторая GRIND ниже первой
    grind = [h for h in hyps if h["categories"] == ["GRIND"]]
    assert grind[1]["scores"]["diversity_adj"] == -5
    base_flot = next(h for h in hyps if h["categories"] == ["FLOT"])
    base_prio = base_flot["scores"]["priority"]

    # 👍 эксперта поднимает категорию
    hyps2 = [card(1, "GRIND", 100), card(3, "FLOT", 100)]
    rank(hyps2, feedback={"FLOT": {"up": 2, "down": 0}})
    flot = next(h for h in hyps2 if h["categories"] == ["FLOT"])
    assert flot["scores"]["feedback_adj"] == 6
    assert flot["scores"]["priority"] > base_prio
    assert flot["rank"] == 1


def test_infer_category(gen):
    infer = gen["analyze"].infer_category
    assert infer("установить контактный чан и увеличить время флотации") == "FLOT"
    assert infer("подобрать собиратель для шламов") == "REAGENT"
    assert infer("заменить футеровку и шары мельницы") == "GRIND"
    assert infer("поменять насадки гидроциклонов") == "CLASSIFY"
    assert infer("возврат песковой части хвостов") == "TAILS"


def test_analyze_arbitrary_hypothesis(gen):
    """Любая гипотеза эксперта получает эффект, обоснование и оценки."""
    d = gen["diagnosis"].diagnose(make_parsed())
    card = gen["analyze"].analyze_hypothesis(
        d, make_kb(),
        "Если установить контактный чан перед контрольной флотацией, "
        "то потери раскрытого металла снизятся на 8-12%", seq=1)
    assert card["status"] == "expert_added"
    assert card["categories"] == ["FLOT"]
    # адресуемый металл посчитан по ячейкам (раскрытый в средних+тонких классах)
    assert card["scores"]["impact_t"] > 0
    assert card["evidence"], "обоснование обязательно"
    assert card["expected_effect"]["addressable_t"]["ni"] <= 6000


def test_generate_llm_off(gen):
    d = gen["diagnosis"].diagnose(make_parsed())
    result = gen["generator"].generate(d, make_kb(), use_llm=False,
                                       project={"target_kpi": "KPI",
                                                "constraints": ["c1"]})
    assert result["engine"] == "rule-based"
    assert result["project"]["target_kpi"] == "KPI"
    assert result["cells"], "ячейки нужны фронту для heatmap"
    ranks = [h["rank"] for h in result["hypotheses"]]
    assert ranks == list(range(1, len(ranks) + 1))
