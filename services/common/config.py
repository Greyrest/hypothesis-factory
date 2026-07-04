from __future__ import annotations

import os
from pathlib import Path


def env(name: str, default: str) -> str:
    return os.getenv(name, default)


DATA_DIR = Path(env("HF_DATA_DIR", ".runtime/data")).resolve()
DB_PATH = Path(env("HF_DB_PATH", ".runtime/hypothesis_factory.sqlite3")).resolve()

INGESTION_URL = env("HF_INGESTION_URL", "http://localhost:8001")
KNOWLEDGE_URL = env("HF_KNOWLEDGE_URL", "http://localhost:8002")
HYPOTHESIS_URL = env("HF_HYPOTHESIS_URL", "http://localhost:8003")
MODEL_RUNTIME_URL = env("HF_MODEL_RUNTIME_URL", "http://localhost:8004")


def prepare_runtime() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

