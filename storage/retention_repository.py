"""Retention application with dry-run default, real deletions and audit trail."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.retention import DEFAULT_POLICY, PrunePlan, validate_policy
from core.timeutil import utc_now
from storage.database import get_connection
from storage.repositories import set_setting

__all__ = ["apply_prune", "retention_stats"]

_TABLES = ("rule_findings", "collector_runs", "cycle_runs", "notification_log", "audit_log")
_CHUNK = 5000


def retention_stats(
    db_path: str | Path | None = None,
    policy: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    config = policy or DEFAULT_POLICY
    reference = now or utc_now()
    with closing(get_connection(db_path)) as connection:
        events: dict[str, int] = {}
        for severity in ("low", "medium", "high", "critical"):
            cutoff = (
                reference - timedelta(days=int(config["events"][f"{severity}_days"]))
            ).isoformat()
            events[severity] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM events WHERE severity = ?", (severity,)
                ).fetchone()[0]
            )
            events[f"{severity}_old"] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM events e WHERE e.severity = ? AND e.timestamp < ? "
                    "AND e.id NOT IN (SELECT ie.event_id FROM incident_events ie "
                    "JOIN incidents i ON i.id = ie.incident_id "
                    "WHERE i.status IN ('open', 'investigating'))",
                    (severity, cutoff),
                ).fetchone()[0]
            )
        stats: dict[str, Any] = {"events": events}
        for table in _TABLES:
            # table names come from the fixed whitelist above.
            stats[table] = int(
                connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]  # noqa: S608
            )
    return stats


def apply_prune(
    plan: PrunePlan,
    db_path: str | Path | None = None,
    *,
    dry_run: bool = True,
    actor: str = "system",
    policy: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if dry_run:
        return {"applied": False, "delete_counts": plan.delete_counts}
    config = policy or DEFAULT_POLICY
    validate_policy(config)
    reference = now or utc_now()
    deleted: dict[str, int] = {}
    with closing(get_connection(db_path)) as connection, connection:
        for severity in ("low", "medium", "high", "critical"):
            cutoff = (
                reference - timedelta(days=int(config["events"][f"{severity}_days"]))
            ).isoformat()
            removed = 0
            while True:
                cursor = connection.execute(
                    "DELETE FROM events WHERE id IN (SELECT id FROM events e "
                    "WHERE e.severity = ? AND e.timestamp < ? "
                    "AND e.id NOT IN (SELECT ie.event_id FROM incident_events ie "
                    "JOIN incidents i ON i.id = ie.incident_id "
                    "WHERE i.status IN ('open', 'investigating')) LIMIT ?)",
                    (severity, cutoff, _CHUNK),
                )
                if cursor.rowcount == 0:
                    break
                removed += cursor.rowcount
            deleted[f"events_{severity}"] = removed
        for key, days in (
            ("rule_findings", config["findings_days"]),
            ("collector_runs", config["collector_runs_days"]),
            ("cycle_runs", config["cycle_runs_days"]),
            ("notification_log", config["notification_log_days"]),
            ("audit_log", config["audit_days"]),
        ):
            cutoff = (reference - timedelta(days=int(days))).isoformat()
            column = (
                "created_at"
                if key == "rule_findings"
                else (
                    "started_at"
                    if key in {"collector_runs", "cycle_runs"}
                    else ("sent_at" if key == "notification_log" else "ts")
                )
            )
            # column and table are from fixed whitelists above.
            cursor = connection.execute(
                "DELETE FROM " + key + " WHERE " + column + " < ?",  # noqa: S608
                (cutoff,),
            )
            deleted[key] = cursor.rowcount
        if plan.vacuum:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.execute("PRAGMA incremental_vacuum")
        connection.execute(
            "INSERT INTO audit_log(ts, actor, action, target_type, target_id, before_json, "
            "after_json, ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                utc_now().isoformat(),
                actor,
                "retention.prune",
                "retention",
                "policy",
                json.dumps(plan.delete_counts, sort_keys=True),
                json.dumps(deleted, sort_keys=True),
                None,
            ),
        )
    set_setting("retention", config, updated_by=actor, db_path=db_path)
    return {"applied": True, "delete_counts": deleted, "vacuum": plan.vacuum}
