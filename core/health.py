"""Self-monitoring health summary. I/O lives here by spec, not in analysis code."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.timeutil import utc_now
from storage.database import get_connection

__all__ = ["get_health"]


def get_health(db_path: str | Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    reference = now or utc_now()
    reasons: list[str] = []
    try:
        with closing(get_connection(db_path)) as connection:
            events = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
            oldest = connection.execute("SELECT MIN(timestamp) FROM events").fetchone()[0]
            last_cycle = connection.execute(
                "SELECT started_at, status FROM cycle_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            db_size = Path(str(db_path)).stat().st_size if db_path else 0
    except Exception as exc:  # noqa: BLE001 - health must never raise
        return {
            "status": "down",
            "reasons": [f"database error: {type(exc).__name__}"],
            "db": {"size_bytes": 0, "event_count": 0, "oldest_event": None},
        }
    if last_cycle is not None:
        try:
            age = reference - datetime.fromisoformat(last_cycle["started_at"])
        except ValueError:
            age = timedelta(0)
        if age > timedelta(minutes=30) or last_cycle["status"] != "ok":
            reasons.append("engine cycle is stale or last cycle had errors")
    else:
        reasons.append("no engine cycle has run yet")
    if events == 0:
        reasons.append("no events collected yet")
    status = "ok" if not reasons else "degraded"
    return {
        "status": status,
        "reasons": reasons,
        "db": {
            "size_bytes": db_size,
            "event_count": events,
            "oldest_event": oldest,
        },
        "last_cycle": dict(last_cycle) if last_cycle else None,
    }
