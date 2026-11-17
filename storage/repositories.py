"""Repositories for events, collector state, audit rows and app settings.

Every function accepts an optional ``db_path`` and uses parameterised SQL.
Dynamic table/column names come only from fixed whitelists.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.events import OPTIONAL_FIELDS, REQUIRED_FIELDS, validate_event
from core.normalizer import compute_event_hash
from core.timeutil import utc_now
from storage.database import get_connection

__all__ = [
    "count_events",
    "event_time_series",
    "record_collector_run",
    "get_event",
    "get_events_by_ids",
    "get_setting",
    "get_state",
    "list_audit",
    "query_events",
    "save_event",
    "save_events",
    "set_setting",
    "set_state",
    "top_values",
    "write_audit",
]

_ALLOWED_EVENT_KEYS = frozenset((*REQUIRED_FIELDS, *OPTIONAL_FIELDS))
_LIST_FILTERS = frozenset({"event_type", "severity", "source"})
_TEXT_FILTERS = frozenset({"username", "source_ip", "process_name"})
_EVENT_FILTERS = (
    _LIST_FILTERS
    | _TEXT_FILTERS
    | frozenset({"since", "until", "search", "allowlisted", "incident_id"})
)
_TOP_VALUE_FIELDS = frozenset(
    {"source_ip", "username", "process_name", "source", "event_type", "severity"}
)


def _json(value: Any) -> str | None:
    return None if value is None else json.dumps(value, sort_keys=True, default=str)


def _prepare_event(
    event: Mapping[str, Any], severity_source: str, allowlisted: bool
) -> tuple[dict[str, Any], str]:
    if not validate_event(event):
        raise ValueError("invalid event")
    parsed = datetime.fromisoformat(event["timestamp"])
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("event timestamp must be timezone-aware")
    clean = {key: value for key, value in event.items() if key in _ALLOWED_EVENT_KEYS}
    # An explicit non-default source wins; otherwise preserve the resolver's value on the event.
    if severity_source != "default" or not clean.get("severity_source"):
        clean["severity_source"] = severity_source
    return clean, compute_event_hash(clean)


def _insert_event(
    connection: sqlite3.Connection,
    event: Mapping[str, Any],
    severity_source: str,
    allowlisted: bool,
    ingested_at: str,
) -> int | None:
    clean, digest = _prepare_event(event, severity_source, allowlisted)
    cursor = connection.execute(
        "INSERT OR IGNORE INTO events ("
        "timestamp, source, event_type, severity, severity_source, username, source_ip, "
        "process_name, destination_ip, file_path, event_hash, event_data, allowlisted, "
        "ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            clean["timestamp"],
            clean["source"],
            clean["event_type"],
            clean["severity"],
            clean["severity_source"],
            clean.get("username"),
            clean.get("source_ip"),
            clean.get("process_name"),
            clean.get("destination_ip"),
            clean.get("file_path"),
            digest,
            json.dumps(clean, sort_keys=True, default=str),
            int(allowlisted),
            ingested_at,
        ),
    )
    if cursor.rowcount == 0:
        return None
    if cursor.lastrowid is None:  # pragma: no cover - INSERT always assigns a rowid
        raise RuntimeError("event insert did not return a row id")
    return int(cursor.lastrowid)


def save_event(
    event: Mapping[str, Any],
    db_path: str | Path | None = None,
    *,
    severity_source: str = "default",
    allowlisted: bool = False,
) -> int | None:
    """Insert an event, returning its id or None when its hash already exists."""
    with closing(get_connection(db_path)) as connection, connection:
        return _insert_event(connection, event, severity_source, allowlisted, utc_now().isoformat())


def save_events(
    events: Sequence[Mapping[str, Any]],
    db_path: str | Path | None = None,
    *,
    severity_source: str = "default",
    allowlisted: bool = False,
) -> list[int | None]:
    """Insert a batch in one transaction, returning an id or None per event."""
    ingested_at = utc_now().isoformat()
    with closing(get_connection(db_path)) as connection, connection:
        return [
            _insert_event(connection, event, severity_source, allowlisted, ingested_at)
            for event in events
        ]


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    event: dict[str, Any] = json.loads(row["event_data"])
    event["id"] = row["id"]
    event["allowlisted"] = bool(row["allowlisted"])
    return event


def get_event(event_id: int, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Return the full stored event, or None when the id is unknown."""
    with closing(get_connection(db_path)) as connection:
        row = connection.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return None if row is None else _event_from_row(row)


def get_events_by_ids(
    event_ids: Sequence[int], db_path: str | Path | None = None
) -> dict[int, dict[str, Any]]:
    """Return a mapping from requested id to event; unknown ids are omitted."""
    if not event_ids:
        return {}
    placeholders = ", ".join(["?"] * len(event_ids))
    # Safe concatenation: placeholders are only '?' markers; values stay bound.
    statement = "SELECT * FROM events WHERE id IN (" + placeholders + ")"  # noqa: S608
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, tuple(event_ids)).fetchall()
    return {int(row["id"]): _event_from_row(row) for row in rows}


def _build_where(filters: Mapping[str, Any]) -> tuple[list[str], list[Any]]:
    unknown = set(filters) - _EVENT_FILTERS
    if unknown:
        raise ValueError(f"unknown event filter(s): {', '.join(sorted(unknown))}")
    if "incident_id" in filters:
        raise ValueError("incident_id filter requires the Phase 7 incident schema")
    clauses: list[str] = []
    parameters: list[Any] = []
    for key in ("event_type", "severity", "source"):
        values = filters.get(key)
        if values:
            if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
                raise ValueError(key + " filter must be a sequence of values")
            items = list(values)
            placeholders = ", ".join(["?"] * len(items))
            clauses.append(key + " IN (" + placeholders + ")")
            parameters.extend(items)
    for key in ("username", "source_ip", "process_name"):
        if key in filters and filters[key] is not None:
            clauses.append(key + " = ?")
            parameters.append(filters[key])
    if filters.get("since") is not None:
        clauses.append("timestamp >= ?")
        parameters.append(filters["since"])
    if filters.get("until") is not None:
        clauses.append("timestamp <= ?")
        parameters.append(filters["until"])
    if filters.get("search"):
        term = str(filters["search"])
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("json_extract(event_data, '$.description') LIKE ? ESCAPE '\\'")
        parameters.append("%" + escaped + "%")
    if "allowlisted" in filters and filters["allowlisted"] is not None:
        clauses.append("allowlisted = ?")
        parameters.append(int(bool(filters["allowlisted"])))
    return clauses, parameters


def _encode_cursor(timestamp: str, event_id: int) -> str:
    payload = json.dumps({"t": timestamp, "i": event_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return str(payload["t"]), int(payload["i"])
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("invalid cursor") from exc


def query_events(
    filters: Mapping[str, Any] | None = None,
    cursor: str | None = None,
    limit: int = 100,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return ``{items, next_cursor}`` using keyset pagination, never OFFSET."""
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    clauses, parameters = _build_where(filters or {})
    if cursor:
        timestamp, event_id = _decode_cursor(cursor)
        clauses.append("(timestamp < ? OR (timestamp = ? AND id < ?))")
        parameters.extend([timestamp, timestamp, event_id])
    statement = "SELECT * FROM events"
    if clauses:
        statement += " WHERE " + " AND ".join(clauses)
    statement += " ORDER BY timestamp DESC, id DESC LIMIT ?"
    parameters.append(limit + 1)
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, parameters).fetchall()
    items = [_event_from_row(row) for row in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        boundary = rows[limit - 1]
        next_cursor = _encode_cursor(boundary["timestamp"], boundary["id"])
    return {"items": items, "next_cursor": next_cursor}


def count_events(
    filters: Mapping[str, Any] | None = None, db_path: str | Path | None = None
) -> int:
    """Count events matching the same filter whitelist as ``query_events``."""
    clauses, parameters = _build_where(filters or {})
    statement = "SELECT COUNT(*) FROM events"
    if clauses:
        statement += " WHERE " + " AND ".join(clauses)
    with closing(get_connection(db_path)) as connection:
        return int(connection.execute(statement, parameters).fetchone()[0])


def event_time_series(
    filters: Mapping[str, Any] | None = None,
    bucket: str = "hour",
    zero_fill: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, int]:
    """Return counts per hour or day bucket, optionally filling empty buckets."""
    if bucket not in {"hour", "day"}:
        raise ValueError("bucket must be 'hour' or 'day'")
    pattern = "%Y-%m-%dT%H:00:00+00:00" if bucket == "hour" else "%Y-%m-%dT00:00:00+00:00"
    clauses, parameters = _build_where(filters or {})
    statement = "SELECT strftime(?, timestamp) AS bucket, COUNT(*) AS total FROM events"
    if clauses:
        statement += " WHERE " + " AND ".join(clauses)
    statement += " GROUP BY bucket ORDER BY bucket"
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, [pattern, *parameters]).fetchall()
    series = {str(row["bucket"]): int(row["total"]) for row in rows if row["bucket"]}
    if not zero_fill or not series:
        return series
    criteria = filters or {}
    start_text = criteria.get("since", min(series))
    end_text = criteria.get("until", max(series))
    start = datetime.fromisoformat(str(start_text))
    end = datetime.fromisoformat(str(end_text))
    step = timedelta(hours=1) if bucket == "hour" else timedelta(days=1)
    current = start.replace(minute=0, second=0, microsecond=0)
    if bucket == "day":
        current = current.replace(hour=0)
    last = end.replace(minute=0, second=0, microsecond=0)
    if bucket == "day":
        last = last.replace(hour=0)
    filled: dict[str, int] = {}
    while current <= last:
        filled[current.strftime(pattern)] = 0
        current += step
    filled.update(series)
    return filled


def top_values(
    field: str,
    filters: Mapping[str, Any] | None = None,
    limit: int = 10,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return the most common values of a whitelisted promoted column."""
    if field not in _TOP_VALUE_FIELDS:
        raise ValueError(f"unsupported top_values field: {field}")
    if limit < 1:
        raise ValueError("limit must be positive")
    clauses, parameters = _build_where(filters or {})
    # Safe concatenation: field was checked against a fixed whitelist above.
    statement = "SELECT " + field + " AS value, COUNT(*) AS total FROM events"  # noqa: S608
    if clauses:
        statement += " WHERE " + " AND ".join(clauses)
    statement += " GROUP BY " + field + " ORDER BY total DESC, value ASC LIMIT ?"
    parameters.append(limit)
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, parameters).fetchall()
    return [{"value": row["value"], "count": int(row["total"])} for row in rows]


def record_collector_run(
    collector: str,
    started_at: str,
    *,
    finished_at: str | None = None,
    events_found: int = 0,
    events_new: int = 0,
    status: str = "ok",
    message: str | None = None,
    db_path: str | Path | None = None,
) -> int:
    """Append a collector run record (idempotence is provided by event hashes)."""
    with closing(get_connection(db_path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO collector_runs(collector, started_at, finished_at, events_found, "
            "events_new, status, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                collector,
                started_at,
                finished_at or utc_now().isoformat(),
                events_found,
                events_new,
                status,
                message,
            ),
        )
        if cursor.lastrowid is None:  # pragma: no cover - INSERT always assigns a rowid
            raise RuntimeError("collector run insert did not return a row id")
        return int(cursor.lastrowid)


def get_state(key: str, db_path: str | Path | None = None) -> Any:
    """Return persisted collector state, or None when the key is absent."""
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT value_json FROM collector_state WHERE key = ?", (key,)
        ).fetchone()
    return None if row is None else json.loads(row["value_json"])


def set_state(key: str, value: Any, db_path: str | Path | None = None) -> None:
    """Upsert collector state."""
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO collector_state(key, value_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, "
            "updated_at = excluded.updated_at",
            (key, json.dumps(value, sort_keys=True, default=str), utc_now().isoformat()),
        )


def write_audit(
    actor: str,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    before: Any = None,
    after: Any = None,
    ip: str | None = None,
    db_path: str | Path | None = None,
) -> int:
    """Append an audit row; secrets must never be passed in ``before``/``after``."""
    with closing(get_connection(db_path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO audit_log(ts, actor, action, target_type, target_id, "
            "before_json, after_json, ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                utc_now().isoformat(),
                actor,
                action,
                target_type,
                target_id,
                _json(before),
                _json(after),
                ip,
            ),
        )
        if cursor.lastrowid is None:  # pragma: no cover - INSERT always assigns a rowid
            raise RuntimeError("audit insert did not return a row id")
        return int(cursor.lastrowid)


def list_audit(
    filters: Mapping[str, Any] | None = None,
    limit: int = 100,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return latest audit rows with a keyset cursor on ``id``."""
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    criteria = filters or {}
    clauses: list[str] = []
    parameters: list[Any] = []
    for key in ("actor", "target_type"):
        if criteria.get(key):
            clauses.append(key + " = ?")
            parameters.append(criteria[key])
    if criteria.get("action_prefix"):
        clauses.append("action LIKE ?")
        parameters.append(str(criteria["action_prefix"]) + "%")
    if criteria.get("since"):
        clauses.append("ts >= ?")
        parameters.append(criteria["since"])
    if criteria.get("until"):
        clauses.append("ts <= ?")
        parameters.append(criteria["until"])
    statement = "SELECT * FROM audit_log"
    if clauses:
        statement += " WHERE " + " AND ".join(clauses)
    statement += " ORDER BY id DESC LIMIT ?"
    parameters.append(limit + 1)
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, parameters).fetchall()
    items = [
        {
            "id": row["id"],
            "ts": row["ts"],
            "actor": row["actor"],
            "action": row["action"],
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "before": json.loads(row["before_json"]) if row["before_json"] else None,
            "after": json.loads(row["after_json"]) if row["after_json"] else None,
            "ip": row["ip"],
        }
        for row in rows[:limit]
    ]
    next_cursor = None
    if len(rows) > limit:
        next_cursor = (
            base64.urlsafe_b64encode(
                json.dumps({"i": rows[limit - 1]["id"]}, separators=(",", ":")).encode("ascii")
            )
            .decode("ascii")
            .rstrip("=")
        )
    return {"items": items, "next_cursor": next_cursor}


def get_setting(key: str, db_path: str | Path | None = None) -> Any:
    """Return an app setting, or None when the key is absent."""
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT value_json FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
    return None if row is None else json.loads(row["value_json"])


def set_setting(
    key: str,
    value: Any,
    *,
    updated_by: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    """Upsert an app setting."""
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO app_settings(key, value_json, updated_at, updated_by) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
            "value_json = excluded.value_json, updated_at = excluded.updated_at, "
            "updated_by = excluded.updated_by",
            (
                key,
                json.dumps(value, sort_keys=True, default=str),
                utc_now().isoformat(),
                updated_by,
            ),
        )
