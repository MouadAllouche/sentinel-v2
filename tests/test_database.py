"""Tests for database connection setup and migrations (Phase 2)."""

from __future__ import annotations

from pathlib import Path

from core.config import load_settings
from storage.database import default_db_path, get_connection, init_db
from storage.migrations import MIGRATIONS


def test_connection_pragmas(tmp_db: Path) -> None:
    connection = get_connection(tmp_db)
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    # synchronous=NORMAL is 1 in SQLite's numeric PRAGMA view.
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
    connection.close()


def test_init_creates_expected_tables_and_indexes(tmp_db: Path) -> None:
    init_db(tmp_db)
    connection = get_connection(tmp_db)
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {
        "schema_version",
        "events",
        "collector_state",
        "audit_log",
        "app_settings",
        "collector_runs",
        "event_type_defaults",
        "severity_overrides",
        "allowlist_entries",
        "rules",
        "rule_versions",
        "rule_findings",
    } <= tables
    indexes = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert {
        "idx_events_timestamp",
        "idx_events_event_type",
        "idx_events_source",
        "idx_events_severity",
        "idx_events_source_ip",
        "idx_events_username",
        "idx_events_event_type_timestamp",
    } <= indexes
    connection.close()


def test_migrations_are_idempotent(tmp_db: Path) -> None:
    init_db(tmp_db, now="2026-11-17T00:00:00+00:00")
    connection = get_connection(tmp_db)
    before = connection.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    assert connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 4
    connection.close()

    init_db(tmp_db, now="2026-11-18T00:00:00+00:00")
    connection = get_connection(tmp_db)
    after = connection.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    versions = connection.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
    assert after == before
    assert [row[0] for row in versions] == [1, 2, 3, 4]
    connection.close()


def test_migration_upgrades_a_legacy_database(tmp_db: Path) -> None:
    connection = get_connection(tmp_db)
    connection.execute(
        "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
        (0, "2026-11-01T00:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    init_db(tmp_db)
    connection = get_connection(tmp_db)
    assert connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 4
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"events", "collector_runs"} <= tables
    connection.close()


def test_migration_list_has_four_entries() -> None:
    assert len(MIGRATIONS) == 4
    assert all(callable(migration) for migration in MIGRATIONS)


def test_default_db_path_comes_from_settings(monkeypatch: object, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTINEL_DB_PATH", str(tmp_path / "chosen.db"))  # type: ignore[attr-defined]
    assert default_db_path() == tmp_path / "chosen.db"
    settings = load_settings(env={})
    assert default_db_path(settings=settings) == settings.paths.database
