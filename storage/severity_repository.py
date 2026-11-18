"""Persistence for editable severity configuration and the allowlist.

All mutations write an audit row in the same transaction. SQL is parameterised;
dynamic identifiers come from fixed whitelists.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Any

from core.allowlist import Entry, reduce_severity, validate_entry
from core.allowlist import matches as allowlist_matches
from core.conditions import validate_condition
from core.enrichment import enrich_event
from core.events import EVENT_TYPES, VALID_SEVERITIES
from core.severity import (
    DEFAULT_OVERRIDES,
    DEFAULT_TYPE_DEFAULTS,
    Override,
    TypeDefault,
    resolve_severity,
)
from core.timeutil import utc_now
from storage.database import get_connection
from storage.repositories import _build_where, _event_from_row

__all__ = [
    "add_allowlist_entry",
    "create_override",
    "delete_allowlist_entry",
    "delete_override",
    "get_allowlist_entries",
    "get_default",
    "get_defaults",
    "get_overrides",
    "reapply_severity",
    "reset_all_defaults",
    "reset_default",
    "reset_override",
    "seed_defaults",
    "set_default",
    "update_allowlist_entry",
    "update_override",
]


def _audit(
    connection: sqlite3.Connection,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    before: Any,
    after: Any,
) -> None:
    connection.execute(
        "INSERT INTO audit_log(ts, actor, action, target_type, target_id, before_json, "
        "after_json, ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            utc_now().isoformat(),
            actor,
            action,
            target_type,
            target_id,
            None if before is None else json.dumps(before, sort_keys=True, default=str),
            None if after is None else json.dumps(after, sort_keys=True, default=str),
            None,
        ),
    )


def _override_from_row(row: sqlite3.Row) -> Override:
    return Override(
        id=row["id"],
        name=row["name"],
        priority=row["priority"],
        conditions=validate_condition(json.loads(row["conditions_json"])),
        severity=row["severity"],
        enabled=bool(row["enabled"]),
        builtin=bool(row["builtin"]),
        default_definition_json=row["default_definition_json"],
    )


def _entry_from_row(row: sqlite3.Row) -> Entry:
    return validate_entry(
        {
            "id": row["id"],
            "kind": row["kind"],
            "value": row["value"],
            "scope": row["scope"],
            "reason": row["reason"],
            "expires_at": row["expires_at"],
            "enabled": bool(row["enabled"]),
        }
    )


def seed_defaults(db_path: str | Path | None = None) -> dict[str, int]:
    """Insert missing built-in defaults; never overwrite user edits."""
    inserted = {"event_type_defaults": 0, "severity_overrides": 0}
    with closing(get_connection(db_path)) as connection, connection:
        for event_type, entry in DEFAULT_TYPE_DEFAULTS.items():
            cursor = connection.execute(
                "INSERT OR IGNORE INTO event_type_defaults(event_type, severity, points, enabled, "
                "description, default_severity, default_points) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_type,
                    entry.severity,
                    entry.points,
                    int(entry.enabled),
                    entry.description,
                    entry.default_severity,
                    entry.default_points,
                ),
            )
            inserted["event_type_defaults"] += cursor.rowcount
        for override in DEFAULT_OVERRIDES:
            definition = json.loads(override.default_definition_json)
            cursor = connection.execute(
                "INSERT OR IGNORE INTO severity_overrides(id, name, priority, conditions_json, "
                "severity, enabled, builtin, default_definition_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    override.id,
                    override.name,
                    override.priority,
                    json.dumps(definition["conditions"], sort_keys=True),
                    override.severity,
                    int(override.enabled),
                    int(override.builtin),
                    override.default_definition_json,
                ),
            )
            inserted["severity_overrides"] += cursor.rowcount
    return inserted


def _defaults_from_rows(rows: list[sqlite3.Row]) -> dict[str, TypeDefault]:
    return {
        row["event_type"]: TypeDefault(
            event_type=row["event_type"],
            severity=row["severity"],
            points=row["points"],
            description=row["description"] or "",
            default_severity=row["default_severity"],
            default_points=row["default_points"],
            enabled=bool(row["enabled"]),
        )
        for row in rows
    }


def get_defaults(db_path: str | Path | None = None) -> dict[str, TypeDefault]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute("SELECT * FROM event_type_defaults").fetchall()
    return _defaults_from_rows(list(rows))


def get_default(event_type: str, db_path: str | Path | None = None) -> TypeDefault:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM event_type_defaults WHERE event_type = ?", (event_type,)
        ).fetchone()
    if row is None:
        return DEFAULT_TYPE_DEFAULTS[event_type]
    return _defaults_from_rows([row])[event_type]


def set_default(
    event_type: str,
    severity: str,
    points: int,
    *,
    actor: str,
    enabled: bool = True,
    db_path: str | Path | None = None,
) -> None:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type!r}")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"invalid severity: {severity!r}")
    if isinstance(points, bool) or not isinstance(points, int) or not 0 <= points <= 100:
        raise ValueError("points must be an integer between 0 and 100")
    before = get_default(event_type, db_path)
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO event_type_defaults(event_type, severity, points, enabled, description, "
            "default_severity, default_points) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(event_type) DO UPDATE SET severity = excluded.severity, "
            "points = excluded.points, enabled = excluded.enabled",
            (
                event_type,
                severity,
                points,
                int(enabled),
                before.description,
                before.default_severity,
                before.default_points,
            ),
        )
        _audit(
            connection,
            actor,
            "severity.set_default",
            "event_type",
            event_type,
            {"severity": before.severity, "points": before.points},
            {"severity": severity, "points": points},
        )


def reset_default(event_type: str, actor: str, db_path: str | Path | None = None) -> None:
    current = get_default(event_type, db_path)
    builtin = DEFAULT_TYPE_DEFAULTS[event_type]
    set_default(
        event_type,
        current.default_severity or builtin.severity,
        current.default_points if current.default_points is not None else builtin.points,
        actor=actor,
        db_path=db_path,
    )


def reset_all_defaults(actor: str, db_path: str | Path | None = None) -> None:
    for event_type in EVENT_TYPES:
        reset_default(event_type, actor, db_path)


def get_overrides(db_path: str | Path | None = None) -> list[Override]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute("SELECT * FROM severity_overrides ORDER BY priority").fetchall()
    return [_override_from_row(row) for row in rows]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "override"


def _check_override_capacity(priority: int, identifier: str, db_path: str | Path | None) -> None:
    existing = get_overrides(db_path)
    if len(existing) >= 200:
        raise ValueError("at most 200 severity overrides are allowed")
    if any(item.priority == priority and item.id != identifier for item in existing):
        raise ValueError(f"override priority {priority} is already used")


def create_override(data: dict[str, Any], actor: str, db_path: str | Path | None = None) -> str:
    identifier = str(data.get("id") or _slug(str(data["name"])))
    if data["severity"] not in VALID_SEVERITIES:
        raise ValueError(f"invalid severity: {data['severity']!r}")
    _check_override_capacity(int(data["priority"]), identifier, db_path)
    definition = {
        "id": identifier,
        "name": data["name"],
        "priority": int(data["priority"]),
        "conditions": data["conditions"],
        "severity": data["severity"],
    }
    conditions_json = json.dumps(
        validate_condition(data["conditions"]).model_dump(by_alias=True), sort_keys=True
    )
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO severity_overrides(id, name, priority, conditions_json, severity, "
            "enabled, builtin, default_definition_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                identifier,
                definition["name"],
                definition["priority"],
                conditions_json,
                definition["severity"],
                int(data.get("enabled", True)),
                0,
                json.dumps(definition, sort_keys=True),
            ),
        )
        _audit(connection, actor, "override.create", "override", identifier, None, definition)
    return identifier


def update_override(
    identifier: str, changes: dict[str, Any], actor: str, db_path: str | Path | None = None
) -> None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM severity_overrides WHERE id = ?", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown override: {identifier}")
        before = _override_from_row(row)
        values = {
            "name": changes.get("name", row["name"]),
            "priority": changes.get("priority", row["priority"]),
            "severity": changes.get("severity", row["severity"]),
            "enabled": changes.get("enabled", bool(row["enabled"])),
        }
        if values["severity"] not in VALID_SEVERITIES:
            raise ValueError(f"invalid severity: {values['severity']!r}")
        _check_override_capacity(int(values["priority"]), identifier, db_path)
        conditions = changes.get("conditions")
        conditions_json = (
            json.dumps(validate_condition(conditions).model_dump(by_alias=True), sort_keys=True)
            if conditions is not None
            else row["conditions_json"]
        )
        with connection:
            connection.execute(
                "UPDATE severity_overrides SET name = ?, priority = ?, severity = ?, enabled = ?, "
                "conditions_json = ? WHERE id = ?",
                (
                    values["name"],
                    values["priority"],
                    values["severity"],
                    int(values["enabled"]),
                    conditions_json,
                    identifier,
                ),
            )
            _audit(
                connection,
                actor,
                "override.update",
                "override",
                identifier,
                {"severity": before.severity, "priority": before.priority},
                values,
            )


def delete_override(identifier: str, actor: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("DELETE FROM severity_overrides WHERE id = ?", (identifier,))
        _audit(
            connection,
            actor,
            "override.delete",
            "override",
            identifier,
            None,
            {"deleted": identifier},
        )


def reset_override(identifier: str, actor: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM severity_overrides WHERE id = ?", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown override: {identifier}")
        definition = json.loads(row["default_definition_json"])
    update_override(
        identifier,
        {
            "name": definition["name"],
            "priority": definition["priority"],
            "conditions": definition["conditions"],
            "severity": definition["severity"],
            "enabled": True,
        },
        actor,
        db_path,
    )


def get_allowlist_entries(db_path: str | Path | None = None) -> list[Entry]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute("SELECT * FROM allowlist_entries ORDER BY id").fetchall()
    return [_entry_from_row(row) for row in rows]


def add_allowlist_entry(data: dict[str, Any], actor: str, db_path: str | Path | None = None) -> int:
    entry = validate_entry({**data, "id": 0})
    with closing(get_connection(db_path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO allowlist_entries(kind, value, scope, reason, expires_at, created_by, "
            "created_at, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.kind,
                entry.value,
                entry.scope,
                entry.reason,
                entry.expires_at,
                actor,
                utc_now().isoformat(),
                int(entry.enabled),
            ),
        )
        identifier = int(cursor.lastrowid or 0)
        _audit(
            connection,
            actor,
            "allowlist.create",
            "allowlist_entry",
            str(identifier),
            None,
            dict(data),
        )
    return identifier


def update_allowlist_entry(
    identifier: int, changes: dict[str, Any], actor: str, db_path: str | Path | None = None
) -> None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM allowlist_entries WHERE id = ?", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown allowlist entry: {identifier}")
        merged = {
            "id": identifier,
            "kind": changes.get("kind", row["kind"]),
            "value": changes.get("value", row["value"]),
            "scope": changes.get("scope", row["scope"]),
            "reason": changes.get("reason", row["reason"]),
            "expires_at": changes.get("expires_at", row["expires_at"]),
            "enabled": changes.get("enabled", bool(row["enabled"])),
        }
        entry = validate_entry(merged)
        with connection:
            connection.execute(
                "UPDATE allowlist_entries SET kind = ?, value = ?, scope = ?, reason = ?, "
                "expires_at = ?, enabled = ? WHERE id = ?",
                (
                    entry.kind,
                    entry.value,
                    entry.scope,
                    entry.reason,
                    entry.expires_at,
                    int(entry.enabled),
                    identifier,
                ),
            )
            _audit(
                connection,
                actor,
                "allowlist.update",
                "allowlist_entry",
                str(identifier),
                dict(row),
                merged,
            )


def delete_allowlist_entry(identifier: int, actor: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("DELETE FROM allowlist_entries WHERE id = ?", (identifier,))
        _audit(
            connection,
            actor,
            "allowlist.delete",
            "allowlist_entry",
            str(identifier),
            None,
            {"deleted": identifier},
        )


def reapply_severity(
    filters: Mapping[str, Any] | None = None,
    db_path: str | Path | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Recompute stored severities; a dry run never writes."""
    defaults = get_defaults(db_path)
    overrides = get_overrides(db_path)
    entries = get_allowlist_entries(db_path)
    clauses, parameters = _build_where(filters or {})
    statement = "SELECT * FROM events"
    if clauses:
        statement += " WHERE " + " AND ".join(clauses)
    now = utc_now()
    updates: list[tuple[str, str, str, int]] = []
    by_severity: dict[str, dict[str, int]] = {}
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, parameters).fetchall()
        for row in rows:
            event = _event_from_row(row)
            before = str(row["severity"])
            enriched = enrich_event(event)
            severity, source = resolve_severity(enriched, defaults, overrides)
            lowering = next(
                (
                    entry
                    for entry in allowlist_matches(enriched, entries, now)
                    if entry.scope == "lower_severity"
                ),
                None,
            )
            if lowering is not None:
                severity = reduce_severity(severity)
                source = f"allowlist:{lowering.id}"
            by_severity.setdefault(before, {"before": 0, "after": 0})["before"] += 1
            by_severity.setdefault(severity, {"before": 0, "after": 0})["after"] += 1
            if severity != before or source != str(row["severity_source"]):
                stored = {
                    key: value for key, value in event.items() if key not in {"id", "allowlisted"}
                }
                stored["severity"] = severity
                stored["severity_source"] = source
                updates.append(
                    (severity, source, json.dumps(stored, sort_keys=True, default=str), row["id"])
                )
        if not dry_run and updates:
            with connection:
                connection.executemany(
                    "UPDATE events SET severity = ?, severity_source = ?, event_data = ? "
                    "WHERE id = ?",
                    updates,
                )
    return {
        "examined": len(rows),
        "changed": len(updates),
        "by_severity_before_after": by_severity,
    }
