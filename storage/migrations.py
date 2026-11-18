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


MIGRATIONS: list[Migration] = [m001, m002, m003]
