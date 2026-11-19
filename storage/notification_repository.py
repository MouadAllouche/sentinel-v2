"""Notification channel and log persistence."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any

from core.notifications.models import Channel
from core.timeutil import utc_now
from storage.database import get_connection

__all__ = [
    "add_channel",
    "delete_channel",
    "list_channels",
    "list_notifications",
    "log_notification",
    "record_change",
    "update_channel",
]


def add_channel(payload: dict[str, Any], actor: str, db_path: str | Path | None = None) -> int:
    with closing(get_connection(db_path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO notification_channels(name, kind, enabled, config_json, "
            "min_severity, filters_json, throttle_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                payload["name"],
                payload["kind"],
                int(payload.get("enabled", False)),
                json.dumps(payload.get("config", {})),
                payload.get("min_severity", "high"),
                json.dumps(payload.get("filters", {})),
                json.dumps(payload.get("throttle", {})),
            ),
        )
        identifier = int(cursor.lastrowid or 0)
        connection.execute(
            "INSERT INTO audit_log(ts, actor, action, target_type, target_id, before_json, "
            "after_json, ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                utc_now().isoformat(),
                actor,
                "channel.create",
                "notification_channel",
                str(identifier),
                None,
                json.dumps(payload, sort_keys=True),
                None,
            ),
        )
    return identifier


def update_channel(
    identifier: int, changes: dict[str, Any], actor: str, db_path: str | Path | None = None
) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        row = connection.execute(
            "SELECT * FROM notification_channels WHERE id = ?", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError("unknown notification channel")
        connection.execute(
            "UPDATE notification_channels SET name = ?, kind = ?, enabled = ?, config_json = ?, "
            "min_severity = ?, filters_json = ?, throttle_json = ? WHERE id = ?",
            (
                changes.get("name", row["name"]),
                changes.get("kind", row["kind"]),
                int(changes.get("enabled", row["enabled"])),
                json.dumps(changes.get("config", json.loads(row["config_json"]))),
                changes.get("min_severity", row["min_severity"]),
                json.dumps(changes.get("filters", json.loads(row["filters_json"]))),
                json.dumps(changes.get("throttle", json.loads(row["throttle_json"]))),
                identifier,
            ),
        )
        connection.execute(
            "INSERT INTO audit_log(ts, actor, action, target_type, target_id, before_json, "
            "after_json, ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                utc_now().isoformat(),
                actor,
                "channel.update",
                "notification_channel",
                str(identifier),
                json.dumps(dict(row), sort_keys=True),
                json.dumps(changes, sort_keys=True),
                None,
            ),
        )


def delete_channel(identifier: int, actor: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("DELETE FROM notification_channels WHERE id = ?", (identifier,))
        connection.execute(
            "INSERT INTO audit_log(ts, actor, action, target_type, target_id, before_json, "
            "after_json, ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                utc_now().isoformat(),
                actor,
                "channel.delete",
                "notification_channel",
                str(identifier),
                None,
                json.dumps({"deleted": identifier}),
                None,
            ),
        )


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
