"""Notification channel and log persistence."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any

from core.notifications.models import Channel
from core.timeutil import utc_now
from storage.database import get_connection

__all__ = ["list_channels", "log_notification", "list_notifications", "record_change"]


def list_channels(db_path: str | Path | None = None) -> list[Channel]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute("SELECT * FROM notification_channels ORDER BY id").fetchall()
    return [
        Channel(
            id=row["id"],
            name=row["name"],
            kind=row["kind"],
            enabled=bool(row["enabled"]),
            config=json.loads(row["config_json"]),
            min_severity=row["min_severity"],
            filters=json.loads(row["filters_json"]),
            throttle=json.loads(row["throttle_json"]),
        )
        for row in rows
    ]


def log_notification(
    channel_id: int,
    incident_id: int | None,
    status: str,
    detail: str,
    db_path: str | Path | None = None,
) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO notification_log(channel_id, incident_id, sent_at, status, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (channel_id, incident_id, utc_now().isoformat(), status, detail),
        )


def list_notifications(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM notification_log ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return [dict(row) for row in rows]


def record_change(kind: str, ref_id: int, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO changes(kind, ref_id, at) VALUES (?, ?, ?)",
            (kind, ref_id, utc_now().isoformat()),
        )
