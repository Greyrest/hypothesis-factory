"""Экспорт результатов: JSON (интеграция), CSV (задачи), Markdown (отчёт)."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def export_json(result: dict, path: Path):
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def export_csv(result: dict, path: Path):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
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


def export_markdown(result: dict, path: Path):
    fmt = lambda v: f"{v:,.0f}".replace(",", " ")
    s = result["summary"]
    lines = [
        f"# Гипотезы снижения потерь металлов — {result['plant']}",
        "",
        f"*Движок генерации: {result['engine']}*",
        "",
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
            f"новизна {sc['novelty']}/5 · риск {sc['risk']}/5",
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

    path.write_text("\n".join(lines), encoding="utf-8")


def export_all(result: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = result["plant"].replace(" ", "_")
    paths = {
        "json": out_dir / f"hypotheses_{stem}.json",
        "csv": out_dir / f"hypotheses_{stem}.csv",
        "md": out_dir / f"report_{stem}.md",
    }
    export_json(result, paths["json"])
    export_csv(result, paths["csv"])
    export_markdown(result, paths["md"])
    return {k: str(v) for k, v in paths.items()}
