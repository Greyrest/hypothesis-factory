"""Фабрика гипотез — сквозной конвейер.

Для каждого примера: парсинг xlsx -> диагностика -> генерация гипотез ->
экспорт (JSON/CSV/MD) -> веб-страница. Плюс index.html и leave-one-out
оценка полноты против эталонных гипотез экспертов.

Запуск:  python pipeline.py [--data DIR] [--out DIR] [--no-llm] [--feedback F]
LLM используется только при наличии ANTHROPIC_API_KEY (иначе rule-based).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from parse_tailings import parse_workbook
from knowledge_base import build_kb, _read_docx_paragraphs
from diagnose import diagnose
from generate import generate
from export_results import export_all
from build_web import build_plant_page, build_index

# темы для leave-one-out сравнения с эталоном (грубое покрытие по ключевым словам)
EVAL_TOPICS = {
    "мельниц|футеровк|шаров|измельчен": "измельчение",
    "гидроциклон|классификат|насадок|классификац|грохо": "классификация",
    "флотац|контактн|чан|плотност|фронт": "флотация",
    "реагент|finfix": "реагенты",
    "дробилк|гранулометр|зазор": "дробление",
    "магнитн|сепарац": "магнитная сепарация",
    "хвост.*возврат|возврат.*хвост": "возврат хвостов",
    "автоматизац|автоматическ|контрол": "автоматизация/контроль",
}


def _topics(texts: list[str]) -> set[str]:
    out = set()
    joined = [t.lower() for t in texts]
    for pattern, topic in EVAL_TOPICS.items():
        if any(re.search(pattern, t) for t in joined):
            out.add(topic)
    return out


def evaluate(results: dict[str, dict], data_dir: Path) -> dict:
    """Покрытие тем эталонного мозгового штурма сгенерированными гипотезами."""
    report = {}
    for hyp_file in sorted(data_dir.glob("Пример */Гипотезы*.docx")):
        label = None
        # сопоставляем docx с фабрикой по xlsx в той же папке
        xlsx = next(hyp_file.parent.glob("Хвосты*.xlsx"), None)
        if xlsx:
            label = xlsx.stem.replace("Хвосты", "").replace("_2", "").strip()
        if label not in results:
            continue
        ref_lines = [l for l in _read_docx_paragraphs(hyp_file)
                     if re.match(r"^\d+\.", l)]
        ref_topics = _topics(ref_lines)
        gen_topics = _topics([h["title"] + " " + h["hypothesis"]
                              for h in results[label]["hypotheses"]])
        covered = ref_topics & gen_topics
        report[label] = {
            "expert_topics": sorted(ref_topics),
            "generated_topics": sorted(gen_topics),
            "covered": sorted(covered),
            "coverage_pct": round(100 * len(covered) / len(ref_topics), 0)
            if ref_topics else None,
        }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="Задача 1. Фабрика гипотез/Задача 1")
    ap.add_argument("--out", default="solution/output")
    ap.add_argument("--no-llm", action="store_true",
                    help="только rule-based (без вызова Claude)")
    ap.add_argument("--feedback", default=None,
                    help="feedback.json с оценками эксперта (из дашборда)")
    args = ap.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(args.out)
    web_dir = out_dir / "web"
    web_dir.mkdir(parents=True, exist_ok=True)

    print("── Фабрика гипотез ──────────────────────────────────────")
    kb = build_kb(data_dir)
    print(f"База знаний: {len(kb['catalog'])} практик, {len(kb['rules'])} правил, "
          f"{len(kb['chunks'])} чанков")

    entries, results = [], {}
    for xlsx in sorted(data_dir.glob("Пример */Хвосты*.xlsx")):
        print(f"\n▶ {xlsx.name}")
        parsed = parse_workbook(xlsx)
        for w in parsed["warnings"]:
            print(f"  ⚠ {w}")
        diag = diagnose(parsed)
        result = generate(diag, kb, use_llm=not args.no_llm,
                          feedback_path=args.feedback)
        results[result["plant"]] = result

        paths = export_all(result, web_dir)
        page = build_plant_page(result, parsed, web_dir, paths)
        entries.append({"plant": result["plant"], "summary": result["summary"],
                        "hypotheses": result["hypotheses"], "page": page.name})

        s = result["summary"]
        print(f"  {result['plant']}: Ni {s['losses_ni_t']:.0f} т "
              f"(извл. {s['recoverable_ni_pct']}%), Cu {s['losses_cu_t']:.0f} т "
              f"(извл. {s['recoverable_cu_pct']}%)")
        print(f"  Гипотез: {len(result['hypotheses'])} · движок: {result['engine']}")
        for h in result["hypotheses"][:3]:
            print(f"    {h['rank']}. [{h['scores']['priority']:.0f}] {h['title']}")

    build_index(entries, web_dir)

    ev = evaluate(results, data_dir)
    (out_dir / "evaluation.json").write_text(
        json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n── Оценка против эталона экспертов (покрытие тем) ─────")
    for plant, e in ev.items():
        print(f"  {plant}: {e['coverage_pct']:.0f}% "
              f"({len(e['covered'])}/{len(e['expert_topics'])} тем: {', '.join(e['covered'])})")

    print(f"\n✅ Готово. Дашборд: {web_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
