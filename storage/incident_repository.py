"""Incident persistence and analyst workflow storage.

All SQL is parameterised; mutations write audit rows in the same transaction.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

from core.incidents import IncidentChange, apply_status_transition
from core.timeutil import utc_now
from storage.database import get_connection


def _record_change(connection: Any, kind: str, identifier: int) -> None:
    connection.execute(
        "INSERT INTO changes(kind, ref_id, at) VALUES (?, ?, ?)",
        (kind, identifier, utc_now().isoformat()),
    )


def _audit(
    connection: Any,
    actor: str,
    action: str,
    incident_id: int,
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
            "incident",
            str(incident_id),
            None if before is None else json.dumps(before, sort_keys=True),
            None if after is None else json.dumps(after, sort_keys=True),
            None,
        ),
    )


__all__ = [
    "add_incident_event",
    "add_note",
    "apply_incidents",
    "get_incident",
    "list_incidents",
    "list_incidents_page",
    "list_notes",
    "list_status_history",
    "set_assignee",
    "set_incident_status",
]


def _row_to_incident(connection: Any, row: Any) -> dict[str, Any]:
    data = dict(row)
    data["mitre"] = json.loads(data.pop("mitre_json", "[]") or "[]")
    event_ids = [
        int(item[0])
        for item in connection.execute(
            "SELECT event_id FROM incident_events WHERE incident_id = ? ORDER BY event_id",
            (row["id"],),
        ).fetchall()
    ]
    data["event_ids"] = event_ids
    rules: list[str] = []
    if event_ids:
        placeholders = ", ".join("?" for _ in event_ids)
        # Only '?' placeholders are interpolated; values stay bound.
        statement = (
            "SELECT DISTINCT rf.rule_id FROM rule_findings rf, "  # noqa: S608
            "json_each(rf.evidence_event_ids_json) j "
            f"WHERE CAST(j.value AS INTEGER) IN ({placeholders}) "
            "ORDER BY rf.rule_id LIMIT 3"
        )
        rules = [str(item[0]) for item in connection.execute(statement, event_ids).fetchall()]
    data["rules_fired"] = rules
    return data


def apply_incidents(
    changes: list[IncidentChange],
    db_path: str | Path | None = None,
    *,
    events: list[dict[str, Any]] | None = None,
    links: list[Any] | None = None,
) -> list[int]:
    """Apply plan changes idempotently; returns affected incident ids."""
    affected: list[int] = []
    with closing(get_connection(db_path)) as connection, connection:
        for change in changes:
            incident = change.incident
            identifier = incident.get("id")
            if change.action == "nochange" and identifier is not None:
                affected.append(int(identifier))
                continue
            values = (
                incident["title"],
                incident["first_seen"],
                incident["last_seen"],
                incident.get("primary_ip"),
                incident.get("primary_username"),
                incident.get("severity", "low"),
                incident.get("summary", ""),
                json.dumps(incident.get("mitre", []), sort_keys=True),
            )
            if change.action == "merge":
                identifier = change.into or incident.get("id")
                if identifier is not None:
                    connection.execute(
                        "UPDATE incidents SET title = ?, first_seen = ?, last_seen = ?, "
                        "primary_ip = ?, primary_username = ?, severity = ?, summary = ?, "
                        "mitre_json = ?, updated_at = ? WHERE id = ?",
                        (*values, utc_now().isoformat(), int(identifier)),
                    )
            else:
                key = str(incident["correlation_key"])
                existing_row = connection.execute(
                    "SELECT id, status FROM incidents WHERE correlation_key = ?", (key,)
                ).fetchone()
                if existing_row is not None and existing_row["status"] in {
                    "resolved",
                    "false_positive",
                    "closed",
                    "merged",
                }:
                    # Reopen as a NEW incident; a deterministic suffix keeps re-runs idempotent.
                    key = f"{key}@reopen:{incident['first_seen']}"
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO incidents(correlation_key, title, status, merged_into, "
                    "first_seen, last_seen, primary_ip, primary_username, severity, risk_score, "
                    "summary, mitre_json, assignee, created_at, updated_at) "
                    "VALUES (?, ?, 'open', NULL, ?, ?, ?, ?, ?, 0, ?, ?, NULL, ?, ?)",
                    (key, *values, utc_now().isoformat(), utc_now().isoformat()),
                )
                identifier = (
                    cursor.lastrowid
                    or connection.execute(
                        "SELECT id FROM incidents WHERE correlation_key = ?", (key,)
                    ).fetchone()[0]
                )
            if identifier is None:
                continue
            identifier = int(identifier)
            if change.action == "create" and cursor.rowcount > 0:
                _record_change(connection, "incident.created", identifier)
            for absorbed in change.absorbed:
                connection.execute(
                    "UPDATE incidents SET status = 'merged', merged_into = ?, updated_at = ? "
                    "WHERE id = ?",
                    (identifier, utc_now().isoformat(), absorbed),
                )
                connection.execute(
                    "INSERT INTO incident_status_history(incident_id, from_status, to_status, "
                    "actor, reason, at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        absorbed,
                        "open",
                        "merged",
                        "system",
                        "merged into incident",
                        utc_now().isoformat(),
                    ),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO incident_events(incident_id, event_id, "
                    "relation_reason, link_strength) SELECT ?, event_id, relation_reason, "
                    "link_strength FROM incident_events WHERE incident_id = ?",
                    (identifier, absorbed),
                )
                connection.execute("DELETE FROM incident_events WHERE incident_id = ?", (absorbed,))
            event_ids = {int(value) for value in incident.get("event_ids", [])}
            link_for_event: dict[int, Any] = {}
            for link in links or []:
                if link.a in event_ids and link.b in event_ids:
                    link_for_event.setdefault(link.a, link)
                    link_for_event.setdefault(link.b, link)
            for event_id in sorted(event_ids):
                link = link_for_event.get(event_id)
                connection.execute(
                    "INSERT OR IGNORE INTO incident_events(incident_id, event_id, "
                    "relation_reason, link_strength) VALUES (?, ?, ?, ?)",
                    (
                        identifier,
                        event_id,
                        link.reason if link else None,
                        link.strength if link else None,
                    ),
                )
            current = connection.execute(
                "SELECT status FROM incidents WHERE id = ?", (identifier,)
            ).fetchone()
            if change.action == "extend" and current is not None and current["status"] != "open":
                connection.execute(
                    "UPDATE incidents SET status = 'open', updated_at = ? WHERE id = ?",
                    (utc_now().isoformat(), identifier),
                )
                connection.execute(
                    "INSERT INTO incident_status_history(incident_id, from_status, to_status, "
                    "actor, reason, at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        identifier,
                        current["status"],
                        "open",
                        "system",
                        "reopened by new evidence",
                        utc_now().isoformat(),
                    ),
                )
            else:
                connection.execute(
                    "UPDATE incidents SET last_seen = ?, updated_at = ? WHERE id = ?",
                    (incident["last_seen"], utc_now().isoformat(), identifier),
                )
            affected.append(identifier)
    return affected


def get_incident(identifier: int, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute("SELECT * FROM incidents WHERE id = ?", (identifier,)).fetchone()
        return None if row is None else _row_to_incident(connection, row)


def list_incidents(
    filters: Mapping[str, Any] | None = None, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    criteria = filters or {}
    clauses: list[str] = []
    parameters: list[Any] = []
    for key in ("status", "severity", "assignee"):
        if key in criteria:
            clauses.append(key + " = ?")
            parameters.append(criteria[key])
    statement = "SELECT * FROM incidents"
    if clauses:
        statement += " WHERE " + " AND ".join(clauses)
    statement += " ORDER BY id"
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, parameters).fetchall()
        return [_row_to_incident(connection, row) for row in rows]


def _encode(page_value: str, identifier: int) -> str:
    payload = json.dumps({"v": page_value, "i": identifier}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def _decode(cursor: str) -> tuple[str, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return str(payload["v"]), int(payload["i"])
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("invalid cursor") from exc


def list_incidents_page(
    filters: Mapping[str, Any] | None = None,
    cursor: str | None = None,
    limit: int = 50,
    sort: str = "risk",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Keyset-paginated incident list for the investigation UI."""
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    if sort not in {"risk", "recent"}:
        raise ValueError("sort must be risk or recent")
    criteria = filters or {}
    clauses: list[str] = []
    parameters: list[Any] = []
    for key in ("status", "severity"):
        values = criteria.get(key)
        if values:
            if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
                raise ValueError(key + " filter must be a sequence")
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{key} IN ({placeholders})")  # noqa: S608 - fixed column names
            parameters.extend(values)
    if criteria.get("assignee"):
        clauses.append("assignee = ?")
        parameters.append(criteria["assignee"])
    if criteria.get("since"):
        clauses.append("last_seen >= ?")
        parameters.append(criteria["since"])
    if criteria.get("until"):
        clauses.append("last_seen <= ?")
        parameters.append(criteria["until"])
    if criteria.get("search"):
        term = str(criteria["search"]).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')")
        parameters.extend([f"%{term}%", f"%{term}%"])
    if criteria.get("needs_attention"):
        clauses.append("status = 'open' AND severity IN ('high', 'critical')")
    column = "risk_score" if sort == "risk" else "last_seen"
    if cursor:
        value, identifier = _decode(cursor)
        clauses.append(f"({column} < ? OR ({column} = ? AND id < ?))")  # noqa: S608
        parameters.extend([value, value, identifier])
    statement = "SELECT * FROM incidents"
    if clauses:
        statement += " WHERE " + " AND ".join(clauses)
    statement += f" ORDER BY {column} DESC, id DESC LIMIT ?"  # noqa: S608 - fixed column
    parameters.append(limit + 1)
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, parameters).fetchall()
        items = [_row_to_incident(connection, row) for row in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        boundary = rows[limit - 1]
        next_cursor = _encode(str(boundary[column]), int(boundary["id"]))
    return {"items": items, "next_cursor": next_cursor}


def add_incident_event(
    incident_id: int,
    event_id: int,
    reason: str,
    strength: str,
    db_path: str | Path | None = None,
) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT OR IGNORE INTO incident_events(incident_id, event_id, relation_reason, "
            "link_strength) VALUES (?, ?, ?, ?)",
            (incident_id, event_id, reason, strength),
        )


def add_note(incident_id: int, author: str, body: str, db_path: str | Path | None = None) -> int:
    with closing(get_connection(db_path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO incident_notes(incident_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (incident_id, author, body, utc_now().isoformat()),
        )
        _audit(connection, author, "incident.note.add", incident_id, None, {"body": body})
        _record_change(connection, "incident.note_added", incident_id)
        return int(cursor.lastrowid or 0)


def list_notes(incident_id: int, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM incident_notes WHERE incident_id = ? ORDER BY id", (incident_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def set_incident_status(
    incident_id: int,
    from_status: str,
    to_status: str,
    actor: str,
    reason: str | None,
    db_path: str | Path | None = None,
) -> None:
    apply_status_transition(from_status, to_status, reason)
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?",
            (to_status, utc_now().isoformat(), incident_id),
        )
        connection.execute(
            "INSERT INTO incident_status_history(incident_id, from_status, to_status, actor, "
            "reason, at) VALUES (?, ?, ?, ?, ?, ?)",
            (incident_id, from_status, to_status, actor, reason, utc_now().isoformat()),
        )
        _audit(
            connection,
            actor,
            "incident.status",
            incident_id,
            {"status": from_status},
            {"status": to_status},
        )
        _record_change(connection, "incident.status_changed", incident_id)


def list_status_history(
    incident_id: int, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM incident_status_history WHERE incident_id = ? ORDER BY id",
            (incident_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_assignee(
    incident_id: int, assignee: str, actor: str, db_path: str | Path | None = None
) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "UPDATE incidents SET assignee = ?, updated_at = ? WHERE id = ?",
            (assignee, utc_now().isoformat(), incident_id),
        )
        _audit(connection, actor, "incident.assignee", incident_id, None, {"assignee": assignee})
        _record_change(connection, "incident.assignee_changed", incident_id)
