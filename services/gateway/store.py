from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results (project_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS graphs (project_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (
  hypothesis_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
CREATE INDEX IF NOT EXISTS idx_feedback_project ON feedback(project_id);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self) -> None:
        with self._connect() as db:
            db.executescript(SCHEMA)

    def put(self, table: str, key_column: str, key: str, body: dict, project_id: str | None = None) -> None:
        allowed = {"projects", "files", "runs", "results", "graphs", "feedback"}
        if table not in allowed or key_column not in {"id", "project_id", "hypothesis_id"}:
            raise ValueError("invalid storage target")
        payload = json.dumps(body, ensure_ascii=False)
        with self._connect() as db:
            if table in {"files", "runs", "feedback"}:
                if project_id is None:
                    raise ValueError("project_id is required")
                db.execute(
                    f"INSERT OR REPLACE INTO {table} ({key_column}, project_id, body) VALUES (?, ?, ?)",
                    (key, project_id, payload),
                )
            else:
                db.execute(
                    f"INSERT OR REPLACE INTO {table} ({key_column}, body) VALUES (?, ?)",
                    (key, payload),
                )

    def get(self, table: str, key_column: str, key: str) -> dict | None:
        allowed = {"projects", "files", "runs", "results", "graphs", "feedback"}
        if table not in allowed or key_column not in {"id", "project_id", "hypothesis_id"}:
            raise ValueError("invalid storage target")
        with self._connect() as db:
            row = db.execute(f"SELECT body FROM {table} WHERE {key_column} = ?", (key,)).fetchone()
        return json.loads(row["body"]) if row else None

    def list(self, table: str, project_id: str | None = None) -> list[dict]:
        if table not in {"projects", "files", "runs", "feedback"}:
            raise ValueError("invalid storage target")
        query = f"SELECT body FROM {table}"
        params: tuple = ()
        if project_id is not None:
            query += " WHERE project_id = ?"
            params = (project_id,)
        query += " ORDER BY rowid DESC"
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [json.loads(row["body"]) for row in rows]

