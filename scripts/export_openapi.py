"""Export reproducible OpenAPI documents for every independently deployed API."""
from __future__ import annotations

import json
from pathlib import Path

from services.gateway.main import app as gateway
from services.hypothesis.main import app as hypothesis
from services.ingestion.main import app as ingestion
from services.knowledge.main import app as knowledge
from services.model_runtime.main import app as model_runtime

APPS = {
    "gateway": gateway,
    "ingestion": ingestion,
    "knowledge": knowledge,
    "hypothesis": hypothesis,
    "model-runtime": model_runtime,
}


def main() -> None:
    output = Path("docs/openapi")
    output.mkdir(parents=True, exist_ok=True)
    for name, app in APPS.items():
        target = output / f"{name}.openapi.json"
        target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(target)


if __name__ == "__main__":
    main()

