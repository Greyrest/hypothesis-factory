"""Обработка произвольной гипотезы эксперта (ТЗ: status = expert_added).

Пользователь вводит любую гипотезу свободным текстом — система сама:
1) определяет категорию мероприятия по терминологии;
2) находит адресуемый металл по ячейкам отчёта (сигналы категории);
3) подбирает обоснование: находки диагностики + retrieval по базе знаний;
4) считает ожидаемый эффект и оценки для общего ранжирования.
"""
from __future__ import annotations

import re

from .generator import CATEGORY_RU, RISKS, ROADMAP, UPLIFT, _addressable
from .retrieval import retrieve

# терминология -> категория (порядок важен: частные раньше общих)
CATEGORY_PATTERNS = [
    (r"реагент|собират|флокул|вспенив|finfix|ксантогенат", "REAGENT"),
    (r"доизмельч|магнитн|сепарац|промпродукт", "REGRIND"),
    (r"возврат.*хвост|хвост.*возврат|переработк.*хвост", "TAILS"),
    (r"гидроциклон|классификатор|классификац|грохо|насадок", "CLASSIFY"),
    (r"дробл|дробилк|гранулометр|зазор|щел", "CRUSH"),
    (r"автоматизац|асу|датчик|онлайн|регулирован", "AUTO"),
    (r"мельниц|измельчен|помол|шаров|футеров|тонин", "GRIND"),
    (r"флотац|пульп|фронт|аэрац|контактн|чан|камер|пенн", "FLOT"),
]

# категория -> сигналы диагностики, на которые она воздействует
CATEGORY_SIGNALS = {
    "GRIND": ["coarse_locked", "mid_locked"],
    "CLASSIFY": ["coarse_locked", "coarse_share"],
    "REGRIND": ["mid_locked", "coarse_locked", "pyrrhotite"],
    "FLOT": ["mid_liberated", "fine_liberated"],
    "REAGENT": ["fine_liberated", "mid_liberated"],
    "CRUSH": ["coarse_locked", "coarse_share"],
    "TAILS": ["tails_recycle"],
    "AUTO": ["coarse_locked", "coarse_share"],
}


def infer_category(text: str) -> str:
    low = text.lower()
    for pattern, cat in CATEGORY_PATTERNS:
        if re.search(pattern, low):
            return cat
    return "CLASSIFY"


def analyze_hypothesis(diagnosis: dict, kb: dict, text: str,
                       title: str | None = None,
                       category: str | None = None,
                       seq: int = 0) -> dict:
    """Свободный текст гипотезы -> полная карточка с эффектом и обоснованием."""
    cat = category if category in CATEGORY_RU else infer_category(text)
    signals = CATEGORY_SIGNALS[cat]
    lo, hi = UPLIFT[cat]

    match = _addressable(diagnosis, signals)
    total_t = match["tons"]["ni"] + match["tons"]["cu"]
    top_f = sorted(match["findings"], key=lambda f: -f["tons"])[:3]

    # обоснование: цифры отчёта + retrieval по терминам гипотезы
    terms = re.findall(r"[а-яёa-z0-9+-]{4,}", text.lower()) + signals
    chunks = retrieve(kb, terms, top_k=2)
    evidence = [{"source": "Отчёт института (xlsx, лист «Итог»)", "fact": f["detail"]}
                for f in top_f]
    evidence += [{"source": ch["source"], "fact": ch["text"][:260]} for ch in chunks]

    mechanism = next((r["text"] for r in kb["rules"]
                      if r["signal"] in {f["signal"] for f in top_f}), "")
    assumption = (
        f"Гипотеза эксперта; адресуемый металл оценён по сигналам категории "
        f"«{CATEGORY_RU[cat]}» ({lo*100:.0f}–{hi*100:.0f}% устранимых потерь). "
        "Требует уточнения испытаниями."
        if total_t else
        "Гипотеза эксперта вне сигналов диагностики: количественная оценка "
        "требует испытаний.")

    return {
        "id": f"{diagnosis['plant']}-expert-{seq}",
        "title": (title or text).strip()[:90],
        "hypothesis": text.strip(),
        "categories": [cat],
        "category_ru": CATEGORY_RU[cat],
        "equipment": "",
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
            "assumption": assumption,
        },
        "scores": {"feasibility": 3, "novelty": 3, "risk": 3,
                   "impact_t": round(total_t, 1)},
        "risks": RISKS[cat],
        "roadmap": ROADMAP[cat],
        "status": "expert_added",
        "sources": sorted({e["source"] for e in evidence}) or
                   ["Гипотеза эксперта"],
        "matched_signals": sorted({f["signal"] for f in top_f}),
        "finding_ids": [f["id"] for f in match["findings"]],
    }
