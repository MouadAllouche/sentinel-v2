"""Persistence for versioned rules and their findings.

All SQL is parameterised; every mutation writes an audit row in the same
transaction. Custom rules are soft-deleted because findings reference them.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Any

from core.rules.defaults import DEFAULT_RULES
from core.rules.models import Rule, validate_rule
from core.rules.threshold import Finding
from core.timeutil import utc_now
from storage.database import get_connection

__all__ = [
    "create_rule",
    "delete_rule",
    "get_events_for_rules",
    "get_rule",
    "get_rule_versions",
    "list_findings",
    "list_rules",
    "reset_all_builtin_rules",
    "reset_rule",
    "restore_rule_version",
    "save_findings",
    "seed_rules",
    "set_rule_enabled",
    "update_rule",
]


def _audit(
    connection: sqlite3.Connection,
    actor: str,
    action: str,
    identifier: str,
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
            "rule",
            identifier,
            None if before is None else json.dumps(before, sort_keys=True, default=str),
            None if after is None else json.dumps(after, sort_keys=True, default=str),
            None,
        ),
    )


def _rule_from_row(row: sqlite3.Row) -> Rule:
    definition = json.loads(row["definition_json"])
    definition["version"] = row["version"]
    definition["builtin"] = bool(row["builtin"])
    definition["default_definition_json"] = row["default_definition_json"]
    return Rule.model_validate(definition)


def _definition_for(rule: Rule) -> dict[str, Any]:
    data = rule.model_dump()
    data.pop("version", None)
    data.pop("builtin", None)
    data.pop("default_definition_json", None)
    return data


def seed_rules(db_path: str | Path | None = None) -> dict[str, int]:
    """Insert missing built-in rules; never overwrite edits."""
    inserted = 0
    with closing(get_connection(db_path)) as connection, connection:
        for definition in DEFAULT_RULES:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO rules(id, name, kind, enabled, builtin, version, "
                "definition_json, default_definition_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    definition["id"],
                    definition["name"],
                    definition["kind"],
                    int(definition.get("enabled", True)),
                    1,
                    1,
                    json.dumps(definition, sort_keys=True, default=str),
                    definition["default_definition_json"],
                    utc_now().isoformat(),
                    utc_now().isoformat(),
                ),
            )
            inserted += cursor.rowcount
    return {"rules": inserted}


def get_rule(identifier: str, db_path: str | Path | None = None) -> Rule | None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM rules WHERE id = ? AND deleted_at IS NULL", (identifier,)
        ).fetchone()
    return None if row is None else _rule_from_row(row)


def list_rules(
    filters: Mapping[str, Any] | None = None, db_path: str | Path | None = None
) -> list[Rule]:
    criteria = filters or {}
    clauses = ["deleted_at IS NULL"]
    parameters: list[Any] = []
    for key in ("kind", "builtin", "enabled"):
        if key in criteria:
            clauses.append(key + " = ?")
            parameters.append(
                int(criteria[key]) if key in {"builtin", "enabled"} else criteria[key]
            )
    # Safe concatenation: keys come from a fixed whitelist; values stay bound.
    statement = "SELECT * FROM rules WHERE " + " AND ".join(clauses) + " ORDER BY id"  # noqa: S608
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, parameters).fetchall()
    return [_rule_from_row(row) for row in rows]


def create_rule(definition: dict[str, Any], actor: str, db_path: str | Path | None = None) -> str:
    rule, _warnings = validate_rule(definition)
    data = _definition_for(rule)
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO rules(id, name, kind, enabled, builtin, version, definition_json, "
            "default_definition_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rule.id,
                rule.name,
                rule.kind,
                int(rule.enabled),
                0,
                1,
                json.dumps(data, sort_keys=True, default=str),
                json.dumps(definition, sort_keys=True, default=str),
                utc_now().isoformat(),
                utc_now().isoformat(),
            ),
        )
        connection.execute(
            "INSERT INTO rule_versions(rule_id, version, definition_json, changed_by, changed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                rule.id,
                1,
                json.dumps(data, sort_keys=True, default=str),
                actor,
                utc_now().isoformat(),
            ),
        )
        _audit(connection, actor, "rule.create", rule.id, None, data)
    return rule.id


def _update(
    identifier: str, definition: dict[str, Any], actor: str, db_path: str | Path | None, action: str
) -> None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM rules WHERE id = ? AND deleted_at IS NULL", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown rule: {identifier}")
        rule, _warnings = validate_rule(definition)
        if rule.id != identifier:
            raise ValueError("rule id is immutable")
        new_version = row["version"] + 1
        data = _definition_for(rule)
        with connection:
            connection.execute(
                "UPDATE rules SET name = ?, kind = ?, enabled = ?, version = ?, "
                "definition_json = ?, updated_at = ? WHERE id = ?",
                (
                    rule.name,
                    rule.kind,
                    int(rule.enabled),
                    new_version,
                    json.dumps(data, sort_keys=True, default=str),
                    utc_now().isoformat(),
                    identifier,
                ),
            )
            connection.execute(
                "INSERT INTO rule_versions(rule_id, version, definition_json, changed_by, "
                "changed_at) VALUES (?, ?, ?, ?, ?)",
                (
                    identifier,
                    new_version,
                    json.dumps(data, sort_keys=True, default=str),
                    actor,
                    utc_now().isoformat(),
                ),
            )
            _audit(connection, actor, action, identifier, json.loads(row["definition_json"]), data)


def update_rule(
    identifier: str, definition: dict[str, Any], actor: str, db_path: str | Path | None = None
) -> None:
    _update(identifier, definition, actor, db_path, "rule.update")


def set_rule_enabled(
    identifier: str, enabled: bool, actor: str, db_path: str | Path | None = None
) -> None:
    current = get_rule(identifier, db_path)
    if current is None:
        raise ValueError(f"unknown rule: {identifier}")
    definition = _definition_for(current)
    definition["enabled"] = enabled
    _update(identifier, definition, actor, db_path, "rule.enable" if enabled else "rule.disable")


def delete_rule(identifier: str, actor: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute("SELECT * FROM rules WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise ValueError(f"unknown rule: {identifier}")
        if row["deleted_at"] is not None:
            return
        if row["builtin"]:
            raise ValueError("built-in rules can only be disabled, not deleted")
        with connection:
            connection.execute(
                "UPDATE rules SET deleted_at = ?, updated_at = ? WHERE id = ?",
                (utc_now().isoformat(), utc_now().isoformat(), identifier),
            )
            _audit(
                connection,
                actor,
                "rule.delete",
                identifier,
                json.loads(row["definition_json"]),
                {"deleted": True},
            )


def reset_rule(identifier: str, actor: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM rules WHERE id = ? AND deleted_at IS NULL", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown rule: {identifier}")
        definition = json.loads(row["default_definition_json"])
    _update(identifier, definition, actor, db_path, "rule.reset")


def reset_all_builtin_rules(actor: str, db_path: str | Path | None = None) -> int:
    """Restore every built-in rule to its seed definition; returns the count."""
    builtins = [rule.id for rule in list_rules(db_path=db_path) if rule.builtin]
    for identifier in builtins:
        reset_rule(identifier, actor, db_path)
    return len(builtins)


def get_rule_versions(identifier: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM rule_versions WHERE rule_id = ? ORDER BY version", (identifier,)
        ).fetchall()
    return [dict(row) for row in rows]


def restore_rule_version(
    identifier: str, version: int, actor: str, db_path: str | Path | None = None
) -> int:
    """Restore an older definition as a new version (never rewrites history)."""
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM rules WHERE id = ? AND deleted_at IS NULL", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown rule: {identifier}")
        snapshot = connection.execute(
            "SELECT definition_json FROM rule_versions WHERE rule_id = ? AND version = ?",
            (identifier, version),
        ).fetchone()
        if snapshot is None:
            raise ValueError(f"unknown rule version: {identifier}@{version}")
        definition = json.loads(snapshot["definition_json"])
        rule, _warnings = validate_rule(definition)
        new_version = int(row["version"]) + 1
        data = _definition_for(rule)
        with connection:
            connection.execute(
                "UPDATE rules SET name = ?, kind = ?, enabled = ?, version = ?, "
                "definition_json = ?, updated_at = ? WHERE id = ?",
                (
                    rule.name,
                    rule.kind,
                    int(row["enabled"]),
                    new_version,
                    json.dumps(data, sort_keys=True, default=str),
                    utc_now().isoformat(),
                    identifier,
                ),
            )
            connection.execute(
                "INSERT INTO rule_versions(rule_id, version, definition_json, changed_by, "
                "changed_at) VALUES (?, ?, ?, ?, ?)",
                (
                    identifier,
                    new_version,
                    json.dumps(data, sort_keys=True, default=str),
                    actor,
                    utc_now().isoformat(),
                ),
            )
            _audit(
                connection,
                actor,
                "rule.version_restored",
                identifier,
                json.loads(row["definition_json"]),
                data,
            )
    return new_version


def save_findings(
    findings: list[Finding], db_path: str | Path | None = None
) -> list[tuple[int, bool]]:
    """Insert findings idempotently; returns (id, is_new) per finding."""
    results: list[tuple[int, bool]] = []
    with closing(get_connection(db_path)) as connection, connection:
        for finding in findings:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO rule_findings(rule_id, rule_version, group_key, tier_index, "
                "severity, points, window_start, window_end, observed, evidence_event_ids_json, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    finding.rule_id,
                    finding.rule_version,
                    finding.group_key,
                    finding.tier_index,
                    finding.severity,
                    finding.points,
                    finding.window_start,
                    finding.window_end,
                    finding.observed,
                    json.dumps(finding.evidence_event_ids),
                    utc_now().isoformat(),
                ),
            )
            if cursor.rowcount:
                results.append((int(cursor.lastrowid or 0), True))
                continue
            existing = connection.execute(
                "SELECT id FROM rule_findings WHERE rule_id = ? AND group_key = ? "
                "AND tier_index = ? AND window_start = ?",
                (finding.rule_id, finding.group_key, finding.tier_index, finding.window_start),
            ).fetchone()
            results.append((int(existing["id"]), False))
    return results


def list_findings(
    filters: Mapping[str, Any] | None = None,
    cursor: str | None = None,
    db_path: str | Path | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    criteria = filters or {}
    clauses: list[str] = []
    parameters: list[Any] = []
    for key in ("rule_id", "severity"):
        if key in criteria:
            clauses.append(key + " = ?")
            parameters.append(criteria[key])
    if cursor:
        try:
            last_id = int(cursor)
        except ValueError as exc:
            raise ValueError("invalid findings cursor") from exc
        clauses.append("id < ?")
        parameters.append(last_id)
    statement = "SELECT * FROM rule_findings"
    if clauses:
        statement += " WHERE " + " AND ".join(clauses)
    statement += " ORDER BY id DESC"
    if limit is not None:
        statement += " LIMIT ?"
        parameters.append(limit + 1)
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, parameters).fetchall()
    return [dict(row) for row in (rows[:limit] if limit is not None else rows)]


def get_events_for_rules(since: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return all events at/after ``since`` for rule evaluation (no page cap)."""
    connection = get_connection(db_path)
    rows = connection.execute("SELECT * FROM events WHERE timestamp >= ?", (since,)).fetchall()
    connection.close()
    from storage.repositories import _event_from_row

    return [_event_from_row(row) for row in rows]
