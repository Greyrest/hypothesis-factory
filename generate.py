"""Генерация и приоритизация гипотез.

Двухступенчатая схема:
1. Rule-based генератор (работает всегда, без сети): диагностика × каталог
   проверенных практик × правила базы знаний -> карточки гипотез с обоснованием,
   цитатами, KPI-оценкой и дорожной картой.
2. Опциональное LLM-усиление (Claude Opus 4.8 через anthropic SDK): полирует
   формулировки и добавляет новые гипотезы вне каталога. При ошибке/отсутствии
   ключа молча остаёмся на rule-based.

Ранжирование по критериям ТЗ: потенциальный эффект, реализуемость, риски,
новизна + поправка на экспертную обратную связь (feedback.json).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from knowledge_base import retrieve

# допущение о доле устранимых потерь по категориям решений (низкая/высокая оценка)
UPLIFT = {
    "GRIND": (0.10, 0.25), "CLASSIFY": (0.15, 0.30), "REGRIND": (0.20, 0.35),
    "FLOT": (0.10, 0.25), "REAGENT": (0.05, 0.15), "CRUSH": (0.05, 0.15),
    "TAILS": (0.15, 0.30), "AUTO": (0.05, 0.15),
}

CATEGORY_RU = {
    "GRIND": "Измельчение", "CLASSIFY": "Классификация",
    "REGRIND": "Доизмельчение/сепарация", "FLOT": "Флотация",
    "REAGENT": "Реагентный режим", "CRUSH": "Дробление",
    "TAILS": "Переработка хвостов", "AUTO": "Автоматизация",
}

ROADMAP = {
    "GRIND": ["Аудит режима измельчения и ситовые характеристики разгрузки мельниц",
              "Лабораторные тесты помола с изменёнными параметрами (2-4 нед)",
              "Опытно-промышленные испытания на одной секции (1-2 мес)",
              "Тираж на все секции при подтверждении эффекта"],
    "CLASSIFY": ["Замер гранулометрии питания/слива/песков узла классификации",
                 "Расчёт/подбор параметров (насадки, зазоры, плотность питания)",
                 "Пробная замена на одном аппарате, контроль циркулирующей нагрузки (2-6 нед)",
                 "Тираж при подтверждении снижения проскока"],
    "REGRIND": ["Выделение целевого класса на пробах, минералогический контроль",
                "Лабораторные тесты доизмельчения/магнитной сепарации (4-8 нед)",
                "ТЭО отдельного цикла, подбор оборудования",
                "Опытный участок и промышленное внедрение"],
    "FLOT": ["Хронометраж времени флотации и покамерное опробование",
             "Тесты изменения плотности/расхода воздуха на действующем фронте (2-4 нед)",
             "Перераспределение фронта / монтаж контактных чанов",
             "Закрепление режима в регламенте"],
    "REAGENT": ["Лабораторные флотационные тесты с новым реагентом на текущих хвостах",
                "Подбор дозировок, оценка селективности (4-6 нед)",
                "Опытно-промышленные испытания на одной секции",
                "Корректировка реагентного режима в регламенте"],
    "CRUSH": ["Контроль гранулометрии питания мельниц (рассевы, онлайн-гранулометр)",
              "Настройка/автоматизация зазора дробилок (2-4 нед)",
              "Контроль стабильности и влияния на производительность цикла"],
    "TAILS": ["Опробование текущих хвостов, баланс по классам",
              "Лабораторная классификация и флотация песковой части (4-8 нед)",
              "ТЭО узла классификации хвостов",
              "Монтаж и опытная эксплуатация"],
    "AUTO": ["Обследование контуров контроля и КИПиА",
             "Внедрение/донастройка автоматического регулирования (2-6 нед)",
             "Оценка стабилизации показателей"],
}

RISKS = {
    "GRIND": ["Рост энергозатрат на измельчение", "Риск переизмельчения и роста шламовых потерь"],
    "CLASSIFY": ["Рост циркулирующей нагрузки сверх пропускной способности мельниц",
                 "Износ насадок/оборудования"],
    "REGRIND": ["Капитальные затраты на отдельный цикл", "Дефицит площадей под оборудование"],
    "FLOT": ["Снижение качества концентрата при затягивании флотации",
             "Ограничение по фронту машин"],
    "REAGENT": ["Влияние на селективность и последующие переделы", "Стоимость реагента"],
    "CRUSH": ["Ограничение производительности дробильного передела"],
    "TAILS": ["Разубоживание питания возвратом", "Капитальные затраты"],
    "AUTO": ["Необходимость надёжных датчиков в абразивной среде"],
}


# ------------------------------------------------------------------ rule-based
COARSE = {"+125", "-125+71", "+71", "-71+45"}
MID = {"-45+20", "-20+10"}
FINE = {"-10"}

# сигнал -> предикат по ячейке (поток × класс × форма × элемент)
SIGNAL_CELLS = {
    "coarse_locked": lambda c: c["form"] == "Закрытый Pnt/Cp" and c["cls"] in COARSE,
    "mid_locked": lambda c: c["form"] == "Закрытый Pnt/Cp" and c["cls"] in MID,
    "mid_liberated": lambda c: c["form"] in ("Раскрытый Pnt/Cp", "Миллерит") and c["cls"] in MID,
    "fine_liberated": lambda c: c["form"] == "Раскрытый Pnt/Cp" and c["cls"] in FINE,
    "coarse_share": lambda c: c["form"] in ("Закрытый Pnt/Cp", "Раскрытый Pnt/Cp") and c["cls"] in COARSE,
    "pyrrhotite": lambda c: c["pyrrhotite"] and c["form"] in
                            ("Закрытый Pnt/Cp", "Раскрытый Pnt/Cp", "Миллерит"),
    "tails_recycle": lambda c: c["form"] in ("Закрытый Pnt/Cp", "Раскрытый Pnt/Cp")
                               and c["cls"] in (COARSE | MID),
}


def _addressable(diagnosis: dict, signals: list[str]) -> dict:
    """Адресуемый металл = объединение ячеек отчёта по сигналам (без задвоений)."""
    preds = [SIGNAL_CELLS[s] for s in signals if s in SIGNAL_CELLS]
    out = {"ni": 0.0, "cu": 0.0}
    for cell in diagnosis["cells"]:
        if any(p(cell) for p in preds):
            out[cell["el"]] += cell["tons"]
    used = [f for f in diagnosis["findings"]
            if not f.get("informational") and f["signal"] in signals]
    return {"tons": out, "findings": used}


def rule_based_generate(diagnosis: dict, kb: dict, feedback: dict | None = None) -> list[dict]:
    findings = diagnosis["findings"]
    active_signals = {f["signal"] for f in findings if not f.get("informational")}
    hypotheses = []

    for entry in kb["catalog"]:
        match = _addressable(diagnosis, entry["signals"])
        total_t = match["tons"]["ni"] + match["tons"]["cu"]
        if total_t < 30:
            continue

        cat = entry["categories"][0]
        lo, hi = UPLIFT[cat]
        top_f = sorted(match["findings"], key=lambda f: -f["tons"])[:3]

        # retrieval: правила + справка по термам гипотезы и сигналов
        terms = (entry["title"].lower().split()
                 + [s for f in top_f for s in (f["signal"], f["element"])])
        chunks = retrieve(kb, terms, top_k=3)
        rules_used = [r for r in kb["rules"] if r["signal"] in
                      {f["signal"] for f in top_f}]

        evidence = [{
            "source": "Отчёт института (xlsx, лист «Итог»)",
            "fact": f["detail"],
        } for f in top_f]
        evidence += [{
            "source": r["source"],
            "fact": f"{r['title']}: {r['text'][:220]}…" if len(r["text"]) > 220 else f"{r['title']}: {r['text']}",
        } for r in rules_used[:2]]

        mechanism = (rules_used[0]["text"] if rules_used else
                     "Снижение потерь за счёт устранения выявленного узкого места.")

        hyp = {
            "id": f"{diagnosis['plant']}-{entry['id']}",
            "title": entry["title"],
            "hypothesis": (
                f"Если внедрить «{entry['title'].lower()}», то потери "
                f"{'/'.join(sorted({f['element_ru'] for f in top_f}))} с хвостами "
                f"снизятся на {lo*100:.0f}–{hi*100:.0f}% от адресуемого металла "
                f"({total_t:.0f} т/период)."),
            "categories": entry["categories"],
            "category_ru": CATEGORY_RU[cat],
            "equipment": entry["equipment"],
            "streams": sorted({f["stream"] for f in top_f}),
            "mechanism": mechanism,
            "evidence": evidence,
            "expected_effect": {
                "addressable_t": {k: round(v, 1) for k, v in match["tons"].items()},
                "uplift_pct": [int(lo * 100), int(hi * 100)],
                "kpi_delta_t": {
                    "ni": [round(match["tons"]["ni"] * lo, 1), round(match["tons"]["ni"] * hi, 1)],
                    "cu": [round(match["tons"]["cu"] * lo, 1), round(match["tons"]["cu"] * hi, 1)],
                },
                "kpi": "Снижение потерь металла с отвальными хвостами, т/период",
                "assumption": (
                    f"Допущение: мероприятие категории «{CATEGORY_RU[cat]}» устраняет "
                    f"{lo*100:.0f}–{hi*100:.0f}% адресуемых потерь (оценка по практике "
                    f"аналогичных мероприятий; уточняется испытаниями)."),
            },
            "scores": {
                "feasibility": entry["feasibility"],
                "novelty": entry["novelty"],
                "risk": entry["risk"],
                "impact_t": round(total_t, 1),
            },
            "risks": RISKS[cat] + ([f"Капитальные затраты: {entry['capex']}"]
                                   if entry.get("capex") == "высокий" else []),
            "roadmap": ROADMAP[cat],
            "status": "catalog",
            "sources": sorted({entry["source"]} | {e["source"] for e in evidence}),
            "matched_signals": sorted({f["signal"] for f in top_f}),
            "finding_ids": [f["id"] for f in match["findings"]],
        }
        hypotheses.append(hyp)

    # пробелы: сигнал без гипотез -> шаблонная гипотеза вне каталога
    covered = {s for h in hypotheses for s in h["matched_signals"]}
    gap_templates = {
        "fine_liberated": ("Подбор реагентного режима для флотации шламов "
                           "(собиратели/флокулянты для класса -10 мкм)", "REAGENT"),
        "tails_recycle": ("Классификация хвостов с возвратом песковой части", "TAILS"),
        "pyrrhotite": ("Доизвлечение сульфидов из пирротинового потока "
                       "(магнитная сепарация + доизмельчение)", "REGRIND"),
    }
    for sig, (title, cat) in gap_templates.items():
        if sig in active_signals and sig not in covered:
            match = _addressable(diagnosis, [sig])
            total_t = match["tons"]["ni"] + match["tons"]["cu"]
            if total_t < 30:
                continue
            lo, hi = UPLIFT[cat]
            top_f = sorted(match["findings"], key=lambda f: -f["tons"])[:3]
            hypotheses.append({
                "id": f"{diagnosis['plant']}-gap-{sig}",
                "title": title,
                "hypothesis": f"Если {title.lower()}, то адресуемые потери "
                              f"({total_t:.0f} т) снизятся на {lo*100:.0f}–{hi*100:.0f}%.",
                "categories": [cat], "category_ru": CATEGORY_RU[cat],
                "equipment": "", "streams": sorted({f["stream"] for f in top_f}),
                "mechanism": next((r["text"] for r in kb["rules"] if r["signal"] == sig), ""),
                "evidence": [{"source": "Отчёт института (xlsx)", "fact": f["detail"]}
                             for f in top_f],
                "expected_effect": {
                    "addressable_t": {k: round(v, 1) for k, v in match["tons"].items()},
                    "uplift_pct": [int(lo * 100), int(hi * 100)],
                    "kpi_delta_t": {
                        "ni": [round(match["tons"]["ni"] * lo, 1), round(match["tons"]["ni"] * hi, 1)],
                        "cu": [round(match["tons"]["cu"] * lo, 1), round(match["tons"]["cu"] * hi, 1)]},
                    "kpi": "Снижение потерь металла с отвальными хвостами, т/период",
                    "assumption": "Оценка по аналогии с мероприятиями той же категории."},
                "scores": {"feasibility": 3, "novelty": 4, "risk": 3,
                           "impact_t": round(total_t, 1)},
                "risks": RISKS[cat], "roadmap": ROADMAP[cat],
                "status": "generated",
                "sources": ["Правила базы знаний (пробел в каталоге практик)"],
                "matched_signals": [sig],
                "finding_ids": [f["id"] for f in match["findings"]],
            })

    rank(hypotheses, feedback)
    return hypotheses


# ---------------------------------------------------------------------- rank
def rank(hypotheses: list[dict], feedback: dict | None = None):
    """Приоритет = 0.40 эффект + 0.30 реализуемость + 0.20 (1-риск) + 0.10 новизна."""
    if not hypotheses:
        return
    max_imp = max(h["scores"]["impact_t"] for h in hypotheses) or 1.0
    fb = feedback or {}
    for h in hypotheses:
        s = h["scores"]
        s["impact_norm"] = round(s["impact_t"] / max_imp, 3)
        prio = 100 * (0.40 * s["impact_norm"]
                      + 0.30 * s["feasibility"] / 5
                      + 0.20 * (1 - s["risk"] / 5)
                      + 0.10 * s["novelty"] / 5)
        # экспертная обратная связь по категориям: +/-3 за голос, потолок +/-10
        adj = 0
        for cat in h["categories"]:
            v = fb.get(cat, {})
            adj += 3 * (v.get("up", 0) - v.get("down", 0))
        s["feedback_adj"] = max(-10, min(10, adj))
        s["priority"] = round(prio + s["feedback_adj"], 1)
    hypotheses.sort(key=lambda h: -h["scores"]["priority"])

    # диверсификация: каждая следующая гипотеза той же категории — штраф 5,
    # чтобы топ не состоял из вариаций одного и того же мероприятия
    seen_cat: dict[str, int] = {}
    for h in hypotheses:
        cat = h["categories"][0]
        pen = 5 * seen_cat.get(cat, 0)
        h["scores"]["diversity_adj"] = -pen
        h["scores"]["priority"] = round(h["scores"]["priority"] - pen, 1)
        seen_cat[cat] = seen_cat.get(cat, 0) + 1

    hypotheses.sort(key=lambda h: -h["scores"]["priority"])
    for i, h in enumerate(hypotheses, 1):
        h["rank"] = i


# ------------------------------------------------------------------- LLM step
LLM_MODEL = "claude-opus-4-8"

HYP_SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "base_id": {"type": ["string", "null"],
                                "description": "id rule-based черновика, если это его доработка; null для новой гипотезы"},
                    "title": {"type": "string"},
                    "hypothesis": {"type": "string",
                                   "description": "проверяемая формулировка «Если …, то …» с числами"},
                    "mechanism": {"type": "string"},
                    "category": {"type": "string",
                                 "enum": list(CATEGORY_RU.keys())},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "roadmap": {"type": "array", "items": {"type": "string"}},
                    "novelty": {"type": "integer"},
                    "feasibility": {"type": "integer"},
                    "risk": {"type": "integer"},
                    "rationale": {"type": "string",
                                  "description": "обоснование со ссылками на цифры отчёта"},
                },
                "required": ["base_id", "title", "hypothesis", "mechanism",
                             "category", "risks", "roadmap", "novelty",
                             "feasibility", "risk", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hypotheses"],
    "additionalProperties": False,
}


def llm_enhance(diagnosis: dict, drafts: list[dict], kb: dict,
                feedback: dict | None = None) -> list[dict] | None:
    """Полировка и расширение через Claude. None => остаёмся на rule-based."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()

        ctx = {
            "диагностика": {
                "фабрика": diagnosis["plant"],
                "сводка": diagnosis["summary"],
                "находки": [{k: f[k] for k in
                             ("signal", "element_ru", "stream", "title", "tons",
                              "share_of_losses_pct", "detail")}
                            for f in diagnosis["findings"][:14]],
            },
            "черновики_гипотез": [{
                "id": h["id"], "title": h["title"], "category": h["categories"][0],
                "addressable_t": h["expected_effect"]["addressable_t"],
                "evidence": [e["fact"] for e in h["evidence"][:2]],
            } for h in drafts[:12]],
            "каталог_практик": [f"{e['title']} [{e['source']}]"
                                for e in kb["catalog"]],
            "правила": [f"{r['title']}: {r['text']}" for r in kb["rules"]],
        }

        msg = client.messages.create(
            model=LLM_MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=(
                "Ты — технолог-обогатитель Норникеля. По диагностике потерь металлов "
                "с хвостами флотации доработай черновики гипотез и предложи 1-3 новых "
                "(вне каталога, но реалистичных для медно-никелевой флотации). "
                "Формулировка гипотезы — проверяемая, вида «Если <действие>, то "
                "<метрика> изменится на <оценка>», с конкретными тоннами и классами "
                "крупности из диагностики. rationale — 2-4 предложения со ссылками на "
                "цифры. Оценки novelty/feasibility/risk — целые 1-5. Отвечай по-русски."),
            messages=[{"role": "user",
                       "content": json.dumps(ctx, ensure_ascii=False)}],
            output_config={"format": {"type": "json_schema", "schema": HYP_SCHEMA}},
        )
        if msg.stop_reason == "refusal":
            return None
        text = next(b.text for b in msg.content if b.type == "text")
        items = json.loads(text)["hypotheses"]
    except Exception as e:  # сеть/ключ/квота — не роняем пайплайн
        print(f"  [LLM] пропущено: {type(e).__name__}: {e}")
        return None

    by_id = {h["id"]: h for h in drafts}
    result = []
    for it in items:
        base = by_id.get(it.get("base_id") or "")
        if base:
            h = dict(base)
            h.update(title=it["title"], hypothesis=it["hypothesis"],
                     mechanism=it["mechanism"], risks=it["risks"],
                     roadmap=it["roadmap"], status="llm")
            h["evidence"] = ([{"source": "Обоснование Claude (по данным отчёта)",
                               "fact": it["rationale"]}] + base["evidence"])
            h["scores"] = dict(base["scores"],
                               novelty=it["novelty"], feasibility=it["feasibility"],
                               risk=it["risk"])
        else:
            cat = it["category"]
            h = {
                "id": f"{diagnosis['plant']}-llm-{len(result)}",
                "title": it["title"], "hypothesis": it["hypothesis"],
                "categories": [cat], "category_ru": CATEGORY_RU.get(cat, cat),
                "equipment": "", "streams": [],
                "mechanism": it["mechanism"],
                "evidence": [{"source": "Обоснование Claude (по данным отчёта)",
                              "fact": it["rationale"]}],
                "expected_effect": {
                    "addressable_t": {"ni": 0, "cu": 0},
                    "uplift_pct": list(UPLIFT.get(cat, (0.05, 0.15))),
                    "kpi_delta_t": {"ni": [0, 0], "cu": [0, 0]},
                    "kpi": "Снижение потерь металла с отвальными хвостами",
                    "assumption": "Количественная оценка требует испытаний."},
                "scores": {"feasibility": it["feasibility"], "novelty": it["novelty"],
                           "risk": it["risk"], "impact_t": 0.0},
                "risks": it["risks"], "roadmap": it["roadmap"],
                "status": "llm-new",
                "sources": ["Генерация Claude Opus 4.8 на основе базы знаний"],
                "matched_signals": [], "finding_ids": [],
            }
        result.append(h)

    # не потерять черновики, которые LLM не вернул
    returned_bases = {it.get("base_id") for it in items}
    for h in drafts:
        if h["id"] not in returned_bases:
            result.append(h)

    rank(result, feedback)
    return result


def generate(diagnosis: dict, kb: dict, use_llm: bool = True,
             feedback_path: str | Path | None = None) -> dict:
    feedback = None
    if feedback_path and Path(feedback_path).exists():
        feedback = json.loads(Path(feedback_path).read_text(encoding="utf-8"))

    drafts = rule_based_generate(diagnosis, kb, feedback)
    used = "rule-based"
    if use_llm:
        enhanced = llm_enhance(diagnosis, drafts, kb, feedback)
        if enhanced:
            drafts, used = enhanced, f"rule-based + {LLM_MODEL}"

    return {
        "plant": diagnosis["plant"],
        "engine": used,
        "summary": diagnosis["summary"],
        "hypotheses": drafts[:12],
        "findings": diagnosis["findings"],
    }
