"""Ordered, idempotent SQLite schema migrations.

Each phase appends exactly one migration; applied migrations are never edited.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

Migration = Callable[[sqlite3.Connection], None]


def _ensure_version_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )


def current_version(connection: sqlite3.Connection) -> int:
    _ensure_version_table(connection)
    row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0] or 0)


def _record_version(connection: sqlite3.Connection, version: int, applied_at: str) -> None:
    _ensure_version_table(connection)
    connection.execute(
        "INSERT OR REPLACE INTO schema_version(version, applied_at) VALUES (?, ?)",
        (version, applied_at),
    )


def schema_version(version: int, applied_at: str, db_path: str | Path | None = None) -> None:
    """Record a schema version in the target database (public, parameterised)."""
    from storage.database import get_connection

    with closing(get_connection(db_path)) as connection, connection:
        _record_version(connection, version, applied_at)


def m001(connection: sqlite3.Connection) -> None:
    """Create the phase-2 tables and their query indexes."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "timestamp TEXT NOT NULL, "
        "source TEXT NOT NULL, "
        "event_type TEXT NOT NULL, "
        "severity TEXT NOT NULL, "
        "severity_source TEXT, "
        "username TEXT, "
        "source_ip TEXT, "
        "process_name TEXT, "
        "destination_ip TEXT, "
        "file_path TEXT, "
        "event_hash TEXT NOT NULL UNIQUE, "
        "event_data TEXT NOT NULL, "
        "allowlisted INTEGER NOT NULL DEFAULT 0, "
        "ingested_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS collector_state ("
        "key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS audit_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "ts TEXT NOT NULL, "
        "actor TEXT NOT NULL, "
        "action TEXT NOT NULL, "
        "target_type TEXT, "
        "target_id TEXT, "
        "before_json TEXT, "
        "after_json TEXT, "
        "ip TEXT)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS app_settings ("
        "key TEXT PRIMARY KEY, "
        "value_json TEXT NOT NULL, "
        "updated_at TEXT NOT NULL, "
        "updated_by TEXT)"
    )
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type)",
        "CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)",
        "CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity)",
        "CREATE INDEX IF NOT EXISTS idx_events_source_ip ON events(source_ip)",
        "CREATE INDEX IF NOT EXISTS idx_events_username ON events(username)",
        "CREATE INDEX IF NOT EXISTS idx_events_event_type_timestamp "
        "ON events(event_type, timestamp)",
    ):
        connection.execute(statement)


def m002(connection: sqlite3.Connection) -> None:
    """Create the phase-3 collector run ledger."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS collector_runs ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "collector TEXT NOT NULL, "
        "started_at TEXT NOT NULL, "
        "finished_at TEXT, "
        "events_found INTEGER NOT NULL DEFAULT 0, "
        "events_new INTEGER NOT NULL DEFAULT 0, "
        "status TEXT NOT NULL, "
        "message TEXT)"
    )


def m003(connection: sqlite3.Connection) -> None:
    """Create the phase-4 editable severity and allowlist tables."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS event_type_defaults ("
        "event_type TEXT PRIMARY KEY, "
        "severity TEXT NOT NULL, "
        "points INTEGER NOT NULL, "
        "enabled INTEGER NOT NULL DEFAULT 1, "
        "description TEXT, "
        "default_severity TEXT, "
        "default_points INTEGER)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS severity_overrides ("
        "id TEXT PRIMARY KEY, "
        "name TEXT NOT NULL, "
        "priority INTEGER NOT NULL UNIQUE, "
        "conditions_json TEXT NOT NULL, "
        "severity TEXT NOT NULL, "
        "enabled INTEGER NOT NULL DEFAULT 1, "
        "builtin INTEGER NOT NULL DEFAULT 1, "
        "default_definition_json TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS allowlist_entries ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "kind TEXT NOT NULL, "
        "value TEXT NOT NULL, "
        "scope TEXT NOT NULL, "
        "reason TEXT NOT NULL, "
        "expires_at TEXT, "
        "created_by TEXT, "
        "created_at TEXT NOT NULL, "
        "enabled INTEGER NOT NULL DEFAULT 1)"
    )


def m004(connection: sqlite3.Connection) -> None:
    """Create the phase-5 rule store and findings ledger."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS rules ("
        "id TEXT PRIMARY KEY, "
        "name TEXT NOT NULL, "
        "kind TEXT NOT NULL, "
        "enabled INTEGER NOT NULL DEFAULT 1, "
        "builtin INTEGER NOT NULL DEFAULT 0, "
        "version INTEGER NOT NULL DEFAULT 1, "
        "definition_json TEXT NOT NULL, "
        "default_definition_json TEXT NOT NULL, "
        "created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL, "
        "deleted_at TEXT)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS rule_versions ("
        "rule_id TEXT NOT NULL, "
        "version INTEGER NOT NULL, "
        "definition_json TEXT NOT NULL, "
        "changed_by TEXT, "
        "changed_at TEXT NOT NULL, "
        "PRIMARY KEY(rule_id, version))"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS rule_findings ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "rule_id TEXT NOT NULL, "
        "rule_version INTEGER NOT NULL, "
        "group_key TEXT NOT NULL, "
        "tier_index INTEGER NOT NULL, "
        "severity TEXT NOT NULL, "
        "points INTEGER NOT NULL, "
        "window_start TEXT NOT NULL, "
        "window_end TEXT NOT NULL, "
        "observed INTEGER NOT NULL, "
        "evidence_event_ids_json TEXT NOT NULL, "
        "created_at TEXT NOT NULL, "
        "UNIQUE(rule_id, group_key, tier_index, window_start))"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_rule_findings_rule ON rule_findings(rule_id)"
    )


def m005(connection: sqlite3.Connection) -> None:
    """Create the phase-7 incident store and analyst workflow tables."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS incidents ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "correlation_key TEXT NOT NULL UNIQUE, "
        "title TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'open', "
        "merged_into INTEGER, "
        "first_seen TEXT NOT NULL, "
        "last_seen TEXT NOT NULL, "
        "primary_ip TEXT, "
        "primary_username TEXT, "
        "severity TEXT NOT NULL DEFAULT 'low', "
        "risk_score REAL NOT NULL DEFAULT 0, "
        "summary TEXT, "
        "mitre_json TEXT NOT NULL DEFAULT '[]', "
        "assignee TEXT, "
        "created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS incident_events ("
        "incident_id INTEGER NOT NULL, "
        "event_id INTEGER NOT NULL, "
        "relation_reason TEXT, "
        "link_strength TEXT, "
        "PRIMARY KEY(incident_id, event_id))"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS incident_notes ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "incident_id INTEGER NOT NULL, "
        "author TEXT NOT NULL, "
        "body TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS incident_status_history ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "incident_id INTEGER NOT NULL, "
        "from_status TEXT, "
        "to_status TEXT NOT NULL, "
        "actor TEXT, "
        "reason TEXT, "
        "at TEXT NOT NULL)"
    )


def m006(connection: sqlite3.Connection) -> None:
    """Create the phase-8 baseline summary table."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS baselines ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "metric TEXT NOT NULL, "
        "subject TEXT NOT NULL, "
        "bucket TEXT NOT NULL, "
        "window_start TEXT NOT NULL, "
        "window_end TEXT NOT NULL, "
        "mean REAL NOT NULL, "
        "stddev REAL NOT NULL, "
        "sample_count INTEGER NOT NULL, "
        "buckets_json TEXT NOT NULL DEFAULT '[]', "
        "computed_at TEXT NOT NULL, "
        "UNIQUE(metric, subject, bucket))"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_baselines_metric_subject "
        "ON baselines(metric, subject, window_end)"
    )


def m007(connection: sqlite3.Connection) -> None:
    """Create the phase-9 monitored-path and snapshot tables."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS monitored_paths ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "path TEXT NOT NULL UNIQUE, "
        "kind TEXT NOT NULL, "
        "sensitivity TEXT NOT NULL, "
        "category TEXT NOT NULL, "
        "metadata_only INTEGER NOT NULL DEFAULT 0, "
        "enabled INTEGER NOT NULL DEFAULT 1, "
        "recursive INTEGER NOT NULL DEFAULT 0, "
        "max_entries INTEGER NOT NULL DEFAULT 2000, "
        "builtin INTEGER NOT NULL DEFAULT 0, "
        "default_definition_json TEXT NOT NULL DEFAULT '{}')"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS file_snapshots ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "path TEXT NOT NULL, "
        "exists_flag INTEGER NOT NULL, "
        "sha256 TEXT, "
        "owner TEXT, "
        "group_name TEXT, "
        "mode TEXT, "
        "mtime TEXT, "
        "size INTEGER, "
        "extra_json TEXT NOT NULL, "
        "captured_at TEXT NOT NULL, "
        "is_baseline INTEGER NOT NULL DEFAULT 0)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_path_time ON file_snapshots(path, captured_at)"
    )


def m008(connection: sqlite3.Connection) -> None:
    """Create the phase-10 risk assessment and change-record tables."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS risk_assessments ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "target_type TEXT NOT NULL, "
        "target_id INTEGER NOT NULL, "
        "score REAL NOT NULL, "
        "severity TEXT NOT NULL, "
        "reasons_json TEXT NOT NULL, "
        "computed_at TEXT NOT NULL, "
        "UNIQUE(target_type, target_id))"
    )
    for key, value in (
        ("risk.severity_thresholds", '{"medium": 20, "high": 40, "critical": 70}'),
        ("risk.recency_decay", '{"enabled": false, "half_life_hours": 72}'),
    ):
        connection.execute(
            "INSERT OR IGNORE INTO app_settings(key, value_json, updated_at, updated_by) "
            "VALUES (?, ?, ?, ?)",
            (key, value, "2026-01-01T00:00:00+00:00", "system"),
        )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS risk_changes ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "target_type TEXT NOT NULL, "
        "target_id INTEGER NOT NULL, "
        "from_severity TEXT, "
        "to_severity TEXT NOT NULL, "
        "at TEXT NOT NULL)"
    )


def m009(connection: sqlite3.Connection) -> None:
    """Create the phase-11 operational tables."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS cycle_runs ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "started_at TEXT NOT NULL, "
        "finished_at TEXT NOT NULL, "
        "status TEXT NOT NULL, "
        "steps_json TEXT NOT NULL DEFAULT '[]')"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS notification_channels ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL, "
        "kind TEXT NOT NULL, "
        "enabled INTEGER NOT NULL DEFAULT 0, "
        "config_json TEXT NOT NULL, "
        "min_severity TEXT NOT NULL DEFAULT 'high', "
        "filters_json TEXT NOT NULL DEFAULT '{}', "
        "throttle_json TEXT NOT NULL DEFAULT '{}')"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS notification_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "channel_id INTEGER NOT NULL, "
        "incident_id INTEGER, "
        "finding_id INTEGER, "
        "sent_at TEXT NOT NULL, "
        "status TEXT NOT NULL, "
        "detail TEXT)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS changes ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "kind TEXT NOT NULL, "
        "ref_id INTEGER NOT NULL, "
        "at TEXT NOT NULL)"
    )
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_cycle_runs_started ON cycle_runs(started_at)",
        "CREATE INDEX IF NOT EXISTS idx_notification_log_sent ON notification_log(sent_at)",
        "CREATE INDEX IF NOT EXISTS idx_changes_at ON changes(at)",
    ):
        connection.execute(statement)


def m010(connection: sqlite3.Connection) -> None:
    """Create the phase-12 auth/session tables."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "username TEXT NOT NULL UNIQUE, "
        "password_hash TEXT NOT NULL, "
        "role TEXT NOT NULL, "
        "disabled INTEGER NOT NULL DEFAULT 0, "
        "failed_logins INTEGER NOT NULL DEFAULT 0, "
        "locked_until TEXT, "
        "lock_count INTEGER NOT NULL DEFAULT 0, "
        "created_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS login_failures ("
        "ip TEXT NOT NULL, "
        "username TEXT NOT NULL, "
        "count INTEGER NOT NULL, "
        "first_at TEXT NOT NULL, "
        "PRIMARY KEY(ip, username))"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "id_hash TEXT PRIMARY KEY, "
        "user_id INTEGER NOT NULL, "
        "created_at TEXT NOT NULL, "
        "last_seen TEXT NOT NULL, "
        "expires_at TEXT NOT NULL, "
        "ip TEXT, "
        "user_agent TEXT)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS saved_filters ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER NOT NULL, "
        "name TEXT NOT NULL, "
        "page TEXT NOT NULL, "
        "query_json TEXT NOT NULL)"
    )


MIGRATIONS: list[Migration] = [
    m001,
    m002,
    m003,
    m004,
    m005,
    m006,
    m007,
    m008,
    m009,
    m010,
]
