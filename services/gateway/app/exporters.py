"""Экспорт результатов на лету: JSON (интеграция), CSV (задачи),
Markdown и DOCX (отчёты). Генерируется по запросу GET /export —
на диск ничего не пишется.
"""
from __future__ import annotations

import csv
import io
import json


def to_json(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


def to_csv(result: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["rank", "priority", "title", "category", "hypothesis",
                "addressable_ni_t", "addressable_cu_t",
                "kpi_delta_ni_t_min", "kpi_delta_ni_t_max",
                "kpi_delta_cu_t_min", "kpi_delta_cu_t_max",
                "feasibility_1_5", "novelty_1_5", "risk_1_5",
                "status", "streams", "sources"])
    for h in result["hypotheses"]:
        eff = h["expected_effect"]
        w.writerow([
            h["rank"], h["scores"]["priority"], h["title"], h["category_ru"],
            h["hypothesis"],
            eff["addressable_t"]["ni"], eff["addressable_t"]["cu"],
            eff["kpi_delta_t"]["ni"][0], eff["kpi_delta_t"]["ni"][1],
            eff["kpi_delta_t"]["cu"][0], eff["kpi_delta_t"]["cu"][1],
            h["scores"]["feasibility"], h["scores"]["novelty"],
            h["scores"]["risk"], h["status"],
            "; ".join(h["streams"]), "; ".join(h["sources"]),
        ])
    return buf.getvalue()


def to_markdown(result: dict) -> str:
    fmt = lambda v: f"{v:,.0f}".replace(",", " ")
    s = result["summary"]
    lines = [
        f"# Гипотезы снижения потерь металлов — {result['plant']}",
        "",
        f"*Движок генерации: {result['engine']}*",
        "",
    ]
    proj = result.get("project")
    if proj:
        lines += [f"**Задача:** {proj.get('target_kpi') or '—'}", ""]
        if proj.get("constraints"):
            lines += ["**Ограничения:** " + "; ".join(proj["constraints"]), ""]
    lines += [
        "## Сводка потерь",
        "",
        f"| Показатель | Ni (эл. 28) | Cu (эл. 29) |",
        f"|---|---|---|",
        f"| Потери с хвостами, т | {fmt(s['losses_ni_t'])} | {fmt(s['losses_cu_t'])} |",
        f"| Извлекаемый металл, т | {fmt(s['recoverable_ni_t'])} | {fmt(s['recoverable_cu_t'])} |",
        f"| Доля извлекаемого, % | {s['recoverable_ni_pct']} | {s['recoverable_cu_pct']} |",
        "",
        "## Ключевые находки диагностики",
        "",
    ]
    for f_ in result["findings"][:8]:
        prefix = "(справочно) " if f_.get("informational") else ""
        lines.append(f"- {prefix}**{f_['title']}** — {fmt(f_['tons'])} т "
                     f"({f_['share_of_losses_pct']}% потерь потока). {f_['detail']}")
    lines += ["", "## Гипотезы (по приоритету)", ""]

    for h in result["hypotheses"]:
        eff = h["expected_effect"]
        sc = h["scores"]
        lines += [
            f"### {h['rank']}. {h['title']}",
            "",
            f"**Приоритет: {sc['priority']}** · категория: {h['category_ru']} · "
            f"эффект: {fmt(sc['impact_t'])} т адресуемо · реализуемость {sc['feasibility']}/5 · "
            f"новизна {sc['novelty']}/5 · риск {sc['risk']}/5 · статус: {h['status']}",
            "",
            f"**Гипотеза.** {h['hypothesis']}",
            "",
            f"**Механизм.** {h['mechanism']}",
            "",
            "**Обоснование и источники:**",
        ]
        for e in h["evidence"]:
            lines.append(f"- {e['fact']}  \n  *— {e['source']}*")
        lines += [
            "",
            f"**Ожидаемый KPI.** {eff['kpi']}: Ni −{eff['kpi_delta_t']['ni'][0]:.0f}…{eff['kpi_delta_t']['ni'][1]:.0f} т, "
            f"Cu −{eff['kpi_delta_t']['cu'][0]:.0f}…{eff['kpi_delta_t']['cu'][1]:.0f} т. {eff['assumption']}",
            "",
            "**Риски:** " + "; ".join(h["risks"]),
            "",
            "**Дорожная карта проверки:**",
        ]
        lines += [f"{i}. {step}" for i, step in enumerate(h["roadmap"], 1)]
        lines.append("")

    return "\n".join(lines)


def to_docx(result: dict) -> bytes:
    """DOCX-отчёт (требование ТЗ «Генерация отчётов PDF/DOCX»)."""
    import docx

    doc = docx.Document()
    doc.add_heading(f"Гипотезы снижения потерь металлов — {result['plant']}", 0)
    doc.add_paragraph(f"Движок генерации: {result['engine']}")
    proj = result.get("project")
    if proj:
        doc.add_paragraph(f"Задача: {proj.get('target_kpi') or '—'}")
        if proj.get("constraints"):
            doc.add_paragraph("Ограничения: " + "; ".join(proj["constraints"]))

    s = result["summary"]
    doc.add_heading("Сводка потерь", level=1)
    table = doc.add_table(rows=4, cols=3)
    table.style = "Table Grid"
    rows = [
        ("Показатель", "Ni (эл. 28)", "Cu (эл. 29)"),
        ("Потери с хвостами, т", f"{s['losses_ni_t']:,.0f}", f"{s['losses_cu_t']:,.0f}"),
        ("Извлекаемый металл, т", f"{s['recoverable_ni_t']:,.0f}", f"{s['recoverable_cu_t']:,.0f}"),
        ("Доля извлекаемого, %", str(s["recoverable_ni_pct"]), str(s["recoverable_cu_pct"])),
    ]
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            table.rows[i].cells[j].text = val.replace(",", " ")

    doc.add_heading("Ключевые находки диагностики", level=1)
    for f_ in result["findings"][:8]:
        prefix = "(справочно) " if f_.get("informational") else ""
        doc.add_paragraph(
            f"{prefix}{f_['title']} — {f_['tons']:,.0f} т "
            f"({f_['share_of_losses_pct']}% потерь потока). {f_['detail']}"
            .replace(",", " "), style="List Bullet")

    doc.add_heading("Гипотезы (по приоритету)", level=1)
    for h in result["hypotheses"]:
        sc, eff = h["scores"], h["expected_effect"]
        doc.add_heading(f"{h['rank']}. {h['title']}", level=2)
        doc.add_paragraph(
            f"Приоритет {sc['priority']} · {h['category_ru']} · "
            f"эффект {sc['impact_t']:,.0f} т · реализуемость {sc['feasibility']}/5 · "
            f"новизна {sc['novelty']}/5 · риск {sc['risk']}/5 · статус {h['status']}"
            .replace(",", " "))
        doc.add_paragraph(f"Гипотеза. {h['hypothesis']}")
        doc.add_paragraph(f"Механизм. {h['mechanism']}")
        doc.add_paragraph("Обоснование и источники:")
        for e in h["evidence"]:
            doc.add_paragraph(f"{e['fact']} — {e['source']}", style="List Bullet")
        doc.add_paragraph(
            f"Ожидаемый KPI: Ni −{eff['kpi_delta_t']['ni'][0]:.0f}…"
            f"{eff['kpi_delta_t']['ni'][1]:.0f} т, "
            f"Cu −{eff['kpi_delta_t']['cu'][0]:.0f}…"
            f"{eff['kpi_delta_t']['cu'][1]:.0f} т. {eff['assumption']}")
        doc.add_paragraph("Риски: " + "; ".join(h["risks"]))
        doc.add_paragraph("Дорожная карта проверки:")
        for i, step in enumerate(h["roadmap"], 1):
            doc.add_paragraph(f"{i}. {step}", style="List Number")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
