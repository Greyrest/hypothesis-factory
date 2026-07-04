from __future__ import annotations

from datetime import datetime, timezone


def health(service: str) -> dict:
    return {
        "status": "ok",
        "service": service,
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

