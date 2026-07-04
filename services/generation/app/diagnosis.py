"""Диагностика потерь по разобранному отчёту о хвостах.

Каждая находка (finding) — сигнал с оценкой затронутого компонента в тоннах,
привязкой к классам крупности/формам и ссылкой на цифры отчёта.
Сигналы соответствуют правилам базы знаний (R1..R7).

Список компонентов приходит из ingestion (parsed["components"]) — диагностика
не завязана на конкретные металлы.
"""
from __future__ import annotations

import re

COARSE = {"+125", "-125+71", "+71", "-71+45"}
MID = {"-45+20", "-20+10"}
FINE = {"-10"}

# базовые извлекаемые формы, если компонент не принёс свой список
BASE_RECOVERABLE_FORMS = ["Закрытый Pnt/Cp", "Раскрытый Pnt/Cp"]


def _components_of(parsed: dict) -> list[dict]:
    """Компоненты отчёта; для старых JSON без components — из ключей totals."""
    comps = parsed.get("components")
    if comps:
        return comps
    ids: list[str] = []
    for stream in parsed.get("streams", []):
        for key in stream.get("totals", {}):
            m = re.match(r"^(?!recoverable_)(\w+)_t$", key)
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
    return [{"id": i, "label": i, "unit": "т",
             "recoverable_forms": BASE_RECOVERABLE_FORMS} for i in ids]


def _form_tons(entry: dict, form_key: str, el: str) -> float:
    v = (entry["forms"].get(form_key) or {}).get(f"{el}_t")
    return v or 0.0


def diagnose_stream(stream: dict, plant: str, components: list[dict]) -> list[dict]:
    findings = []
    classes = stream["size_classes"]
    is_pyrrhotite = "пирротин" in stream["name"].lower()

    for comp in components:
        el = comp["id"]
        el_label = comp.get("label") or el
        total = stream["totals"].get(f"{el}_t")
        if not total:
            continue

        coarse_locked = sum(_form_tons(c, "Закрытый Pnt/Cp", el)
                            for c in classes if c["cls"] in COARSE)
        mid_locked = sum(_form_tons(c, "Закрытый Pnt/Cp", el)
                         for c in classes if c["cls"] in MID)
        mid_lib = sum(_form_tons(c, "Раскрытый Pnt/Cp", el)
                      for c in classes if c["cls"] in MID)
        fine_lib = sum(_form_tons(c, "Раскрытый Pnt/Cp", el)
                       for c in classes if c["cls"] in FINE)
        coarse_lib = sum(_form_tons(c, "Раскрытый Pnt/Cp", el)
                         for c in classes if c["cls"] in COARSE)
        pyr_imp = sum(_form_tons(c, "Примесь в пирротине", el) for c in classes)
        millerite = sum(_form_tons(c, "Миллерит", el) for c in classes)

        coarse_mass_share = sum(c.get("share_pct") or 0
                                for c in classes if c["cls"] in COARSE)

        cls_list = lambda group: [c["cls"] for c in classes if c["cls"] in group
                                  and (_form_tons(c, "Закрытый Pnt/Cp", el)
                                       or _form_tons(c, "Раскрытый Pnt/Cp", el))]

        def add(signal, title, tons, detail, classes_involved, forms):
            if tons < max(10.0, 0.01 * total):   # шум отсекаем
                return
            findings.append(dict(
                id=f"{plant}-{stream['name'][:12]}-{el}-{signal}".replace(" ", "_"),
                signal=signal, element=el, element_ru=el_label,
                stream=stream["name"], title=title,
                tons=round(tons, 1),
                share_of_losses_pct=round(100 * tons / total, 1),
                classes=classes_involved, forms=forms, detail=detail,
            ))

        coarse_present = ", ".join(sorted(COARSE & {c["cls"] for c in classes}))
        add("coarse_locked",
            f"Недоизмельчение: закрытый {el_label} в крупных классах",
            coarse_locked,
            f"В классах {coarse_present} закрытый "
            f"(в сростках) металл составляет {coarse_locked:.0f} т — "
            f"{100*coarse_locked/total:.0f}% потерь {el_label} потока. Минерал не "
            f"раскрыт при текущей тонине помола.",
            cls_list(COARSE), ["Закрытый Pnt/Cp"])

        add("fine_liberated",
            f"Шламовые потери: раскрытый {el_label} в классе -10 мкм",
            fine_lib,
            f"Свободный минерал в тоне -10 мкм: {fine_lib:.0f} т "
            f"({100*fine_lib/total:.0f}% потерь). Флотация теряет тонкие частицы; "
            f"возможен вклад переизмельчения.",
            ["-10"], ["Раскрытый Pnt/Cp"])

        add("mid_liberated",
            f"Недофлотация: раскрытый {el_label} во флотационной крупности",
            mid_lib,
            f"Свободный минерал в классах {', '.join(sorted(MID))}: {mid_lib:.0f} т. Частицы "
            f"флотационной крупности не извлечены — признак нехватки времени "
            f"флотации/фронта машин или неоптимальной плотности пульпы.",
            cls_list(MID), ["Раскрытый Pnt/Cp"])

        add("mid_locked",
            f"Сростки в средних классах ({el_label})",
            mid_locked,
            f"Закрытый металл в классах {', '.join(sorted(MID))}: {mid_locked:.0f} т — "
            f"кандидат на доизмельчение промпродукта.",
            cls_list(MID), ["Закрытый Pnt/Cp"])

        if coarse_mass_share >= 25:
            add("coarse_share",
                "Проскок крупных классов через классификацию",
                coarse_locked + coarse_lib,
                f"{coarse_mass_share:.0f}% массы хвостов крупнее 45 мкм — "
                f"классификация пропускает крупные частицы (несут "
                f"{coarse_locked + coarse_lib:.0f} т {el_label}).",
                cls_list(COARSE), ["Закрытый Pnt/Cp", "Раскрытый Pnt/Cp"])

        if is_pyrrhotite:
            rec = stream["totals"].get(f"recoverable_{el}_t") or 0.0
            add("pyrrhotite",
                f"Извлекаемый {el_label} в пирротиновых хвостах",
                rec,
                f"Пирротиновые хвосты содержат {rec:.0f} т извлекаемого "
                f"{el_label} (раскрытые/закрытые сульфиды). Кандидат на "
                f"магнитную сепарацию/доизвлечение в отдельном цикле.",
                [c["cls"] for c in classes], ["Раскрытый Pnt/Cp", "Закрытый Pnt/Cp"])
        elif pyr_imp:
            # справочно: неизвлекаемая примесь (гипотез не порождает)
            findings.append(dict(
                id=f"{plant}-{stream['name'][:12]}-{el}-pyr_info".replace(" ", "_"),
                signal="pyrrhotite_info", element=el, element_ru=el_label,
                stream=stream["name"],
                title=f"Неизвлекаемая примесь {el_label} в пирротине",
                tons=round(pyr_imp, 1),
                share_of_losses_pct=round(100 * pyr_imp / total, 1),
                classes=[], forms=["Примесь в пирротине"],
                detail=f"{pyr_imp:.0f} т {el_label} — изоморфная примесь в "
                       f"пирротине, текущей технологией не извлекается. "
                       f"Исключено из потенциала гипотез.",
                informational=True,
            ))

        millerite_recoverable = "Миллерит" in (comp.get("recoverable_forms")
                                               or BASE_RECOVERABLE_FORMS)
        if millerite > max(10.0, 0.01 * total) and millerite_recoverable:
            add("mid_liberated",
                f"Потери миллерита (извлекаемый {el_label})",
                millerite,
                f"Миллерит (извлекаемая форма {el_label}): {millerite:.0f} т в хвостах.",
                [c["cls"] for c in classes if _form_tons(c, "Миллерит", el)],
                ["Миллерит"])

    return findings


def _cells(parsed: dict, comp_ids: list[str]) -> list[dict]:
    """Плоская таблица (поток × класс × форма × компонент) -> тонны.

    Нужна генератору, чтобы считать адресуемый металл без задвоений,
    когда несколько сигналов указывают на одни и те же ячейки отчёта.
    """
    out = []
    for stream in parsed["streams"]:
        if stream.get("aggregate"):
            continue
        pyr = "пирротин" in stream["name"].lower()
        for entry in stream["size_classes"]:
            for form, vals in entry["forms"].items():
                for el in comp_ids:
                    t = vals.get(f"{el}_t")
                    if t:
                        out.append(dict(stream=stream["name"], pyrrhotite=pyr,
                                        cls=entry["cls"], form=form, el=el,
                                        tons=round(t, 1)))
    return out


def diagnose(parsed: dict) -> dict:
    plant = parsed["plant"]
    components = _components_of(parsed)
    findings = []
    for stream in parsed["streams"]:
        if stream.get("aggregate"):
            continue
        findings.extend(diagnose_stream(stream, plant, components))

    findings.sort(key=lambda f: -f["tons"])

    # сводный потенциал: извлекаемый металл неагрегированных потоков
    active = [s for s in parsed["streams"] if not s.get("aggregate")]
    losses, recoverable, rec_pct = {}, {}, {}
    for comp in components:
        el = comp["id"]
        tot = sum(s["totals"].get(f"{el}_t") or 0.0 for s in active)
        rec = sum(s["totals"].get(f"recoverable_{el}_t") or 0.0 for s in active)
        losses[el] = round(tot, 1)
        recoverable[el] = round(rec, 1)
        rec_pct[el] = round(100 * rec / tot, 1) if tot else 0

    summary = {"losses_t": losses, "recoverable_t": recoverable,
               "recoverable_pct": rec_pct}
    # плоские алиасы для обратной совместимости (их читает фронтенд)
    for el in losses:
        summary[f"losses_{el}_t"] = losses[el]
        summary[f"recoverable_{el}_t"] = recoverable[el]
        summary[f"recoverable_{el}_pct"] = rec_pct[el]

    return {
        "plant": plant,
        "components": components,
        "cells": _cells(parsed, [c["id"] for c in components]),
        "summary": summary,
        "findings": findings,
    }
