"""Диагностика потерь по разобранному отчёту о хвостах.

Каждая находка (finding) — сигнал с оценкой затронутого металла в тоннах,
привязкой к классам крупности/формам и ссылкой на цифры отчёта.
Сигналы соответствуют правилам базы знаний (R1..R7). Перенос diagnose.py
прототипа без изменения алгоритма.
"""
from __future__ import annotations

from hf_domains.mining_flotation.constants import COARSE, EL_RU, FINE, MID


def _form_tons(entry: dict, form_key: str, el: str) -> float:
    v = (entry["forms"].get(form_key) or {}).get(f"{el}_t")
    return v or 0.0


def diagnose_stream(stream: dict, plant: str) -> list[dict]:
    findings = []
    classes = stream["size_classes"]
    is_pyrrhotite = "пирротин" in stream["name"].lower()

    for el in ("ni", "cu"):
        total = stream["totals"][f"{el}_t"]
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
                signal=signal, element=el, element_ru=EL_RU[el],
                stream=stream["name"], title=title,
                tons=round(tons, 1),
                share_of_losses_pct=round(100 * tons / total, 1),
                classes=classes_involved, forms=forms, detail=detail,
            ))

        coarse_present = ", ".join(sorted(COARSE & {c["cls"] for c in classes}))
        add("coarse_locked",
            f"Недоизмельчение: закрытый {EL_RU[el]} в крупных классах",
            coarse_locked,
            f"В классах {coarse_present} закрытый "
            f"(в сростках) металл составляет {coarse_locked:.0f} т — "
            f"{100*coarse_locked/total:.0f}% потерь {EL_RU[el]} потока. Минерал не "
            f"раскрыт при текущей тонине помола.",
            cls_list(COARSE), ["Закрытый Pnt/Cp"])

        add("fine_liberated",
            f"Шламовые потери: раскрытый {EL_RU[el]} в классе -10 мкм",
            fine_lib,
            f"Свободный минерал в тоне -10 мкм: {fine_lib:.0f} т "
            f"({100*fine_lib/total:.0f}% потерь). Флотация теряет тонкие частицы; "
            f"возможен вклад переизмельчения.",
            ["-10"], ["Раскрытый Pnt/Cp"])

        add("mid_liberated",
            f"Недофлотация: раскрытый {EL_RU[el]} во флотационной крупности",
            mid_lib,
            f"Свободный минерал в классах {', '.join(sorted(MID))}: {mid_lib:.0f} т. Частицы "
            f"флотационной крупности не извлечены — признак нехватки времени "
            f"флотации/фронта машин или неоптимальной плотности пульпы.",
            cls_list(MID), ["Раскрытый Pnt/Cp"])

        add("mid_locked",
            f"Сростки в средних классах ({EL_RU[el]})",
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
                f"{coarse_locked + coarse_lib:.0f} т {EL_RU[el]}).",
                cls_list(COARSE), ["Закрытый Pnt/Cp", "Раскрытый Pnt/Cp"])

        if is_pyrrhotite:
            rec = stream["totals"][f"recoverable_{el}_t"]
            add("pyrrhotite",
                f"Извлекаемый {EL_RU[el]} в пирротиновых хвостах",
                rec,
                f"Пирротиновые хвосты содержат {rec:.0f} т извлекаемого "
                f"{EL_RU[el]} (раскрытые/закрытые сульфиды). Кандидат на "
                f"магнитную сепарацию/доизвлечение в отдельном цикле.",
                [c["cls"] for c in classes], ["Раскрытый Pnt/Cp", "Закрытый Pnt/Cp"])
        elif pyr_imp:
            # справочно: неизвлекаемая примесь (гипотез не порождает)
            findings.append(dict(
                id=f"{plant}-{stream['name'][:12]}-{el}-pyr_info".replace(" ", "_"),
                signal="pyrrhotite_info", element=el, element_ru=EL_RU[el],
                stream=stream["name"],
                title=f"Неизвлекаемая примесь {EL_RU[el]} в пирротине",
                tons=round(pyr_imp, 1),
                share_of_losses_pct=round(100 * pyr_imp / total, 1),
                classes=[], forms=["Примесь в пирротине"],
                detail=f"{pyr_imp:.0f} т {EL_RU[el]} — изоморфная примесь в "
                       f"пирротине, текущей технологией не извлекается. "
                       f"Исключено из потенциала гипотез.",
                informational=True,
            ))

        if millerite > max(10.0, 0.01 * total) and el == "ni":
            add("mid_liberated",
                "Потери миллерита (извлекаемый Ni)",
                millerite,
                f"Миллерит (извлекаемая форма Ni): {millerite:.0f} т в хвостах.",
                [c["cls"] for c in classes if _form_tons(c, "Миллерит", el)],
                ["Миллерит"])

    return findings


def _cells(parsed: dict) -> list[dict]:
    """Плоская таблица (поток × класс × форма × элемент) -> тонны.

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
                for el in ("ni", "cu"):
                    t = vals.get(f"{el}_t")
                    if t:
                        out.append(dict(stream=stream["name"], pyrrhotite=pyr,
                                        cls=entry["cls"], form=form, el=el,
                                        tons=round(t, 1)))
    return out


def diagnose(parsed: dict) -> dict:
    plant = parsed["plant"]
    findings = []
    for stream in parsed["streams"]:
        if stream.get("aggregate"):
            continue
        findings.extend(diagnose_stream(stream, plant))

    findings.sort(key=lambda f: -f["tons"])

    # сводный потенциал: извлекаемый металл неагрегированных потоков
    rec_ni = sum(s["totals"]["recoverable_ni_t"] for s in parsed["streams"]
                 if not s.get("aggregate"))
    rec_cu = sum(s["totals"]["recoverable_cu_t"] for s in parsed["streams"]
                 if not s.get("aggregate"))
    tot_ni = sum(s["totals"]["ni_t"] for s in parsed["streams"] if not s.get("aggregate"))
    tot_cu = sum(s["totals"]["cu_t"] for s in parsed["streams"] if not s.get("aggregate"))

    return {
        "plant": plant,
        "cells": _cells(parsed),
        "summary": {
            "losses_ni_t": round(tot_ni, 1), "losses_cu_t": round(tot_cu, 1),
            "recoverable_ni_t": round(rec_ni, 1), "recoverable_cu_t": round(rec_cu, 1),
            "recoverable_ni_pct": round(100 * rec_ni / tot_ni, 1) if tot_ni else 0,
            "recoverable_cu_pct": round(100 * rec_cu / tot_cu, 1) if tot_cu else 0,
        },
        "findings": findings,
    }
