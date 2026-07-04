"""Экспорт OpenAPI-спек всех сервисов в openapi/*.json (без запуска серверов)."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES = ["gateway", "ingestion", "knowledge", "generation", "llm"]


def main():
    out_dir = ROOT / "openapi"
    out_dir.mkdir(exist_ok=True)
    for name in SERVICES:
        svc = ROOT / "services" / name
        sys.path.insert(0, str(svc))
        try:
            for mod in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
                del sys.modules[mod]
            app = importlib.import_module("app.main").app
            spec = app.openapi()
            path = out_dir / f"{name}.json"
            path.write_text(json.dumps(spec, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            print(f"  {path.relative_to(ROOT)}  ({spec['info']['title']})")
        finally:
            sys.path.remove(str(svc))


if __name__ == "__main__":
    main()
