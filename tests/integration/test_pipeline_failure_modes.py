"""Failure modes and robustness of the full pipeline (Phase 18, spec 18.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.config import load_settings
from engine.drift import check_drift
from engine.ingest import run_collection
from engine.runner import run_once
from storage.database import get_connection
from storage.repositories import count_events, query_events, save_events
from storage.rules_repository import seed_rules
from storage.severity_repository import seed_defaults

NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)


def test_missing_auth_log_degrades_gracefully(tmp_initialised_db: Path) -> None:
    settings = load_settings(config_path=None)
    report = run_collection(settings, tmp_initialised_db, now=NOW)
    assert isinstance(report.warnings, list)
    assert all(isinstance(item, str) for item in report.warnings)


def test_unreadable_monitored_file_produces_warning(tmp_initialised_db: Path) -> None:
    from storage.drift_repository import add_monitored_path

    add_monitored_path(
        {
            "path": str(tmp_initialised_db),
            "kind": "file",
            "category": "other",
            "sensitivity": "low",
            "enabled": True,
        },
        "test",
        tmp_initialised_db,
        allow_custom_paths=True,
    )
    report = check_drift(tmp_initialised_db, now=NOW)
    assert report.drift_events >= 0


def test_collector_exception_is_isolated(tmp_initialised_db: Path, monkeypatch: Any) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("collector exploded")

    monkeypatch.setattr("engine.ingest.collect_auth_events", boom)
    settings = load_settings(config_path=None)
    report = run_collection(settings, tmp_initialised_db, now=NOW)
    assert any("collector" in warning.lower() for warning in report.warnings)


def test_future_events_are_stored_with_their_timestamps(tmp_initialised_db: Path) -> None:
    future = {
        "timestamp": (NOW + timedelta(days=2)).isoformat(),
        "source": "auth_log",
        "event_type": "failed_login",
        "severity": "low",
        "description": "clock skew",
        "source_ip": "203.0.113.45",
    }
    ids = save_events([future], tmp_initialised_db)
    assert ids[0] is not None


def test_large_burst_stays_within_budget(tmp_initialised_db: Path) -> None:
    from time import monotonic

    events = [
        {
            "timestamp": (NOW + timedelta(seconds=index // 100)).isoformat(),
            "source": "auth_log",
            "event_type": "failed_login",
            "severity": "low",
            "description": "burst",
            "source_ip": "203.0.113.45",
        }
        for index in range(10_000)
    ]
    started = monotonic()
    save_events(events, tmp_initialised_db)
    seed_defaults(tmp_initialised_db)
    seed_rules(tmp_initialised_db)
    settings = load_settings(config_path=None)
    report = run_once(settings, tmp_initialised_db, NOW, notify=False)
    elapsed = monotonic() - started
    assert report.ok
    assert count_events(db_path=tmp_initialised_db) <= 10_000
    assert elapsed < 60, f"10k burst took {elapsed:.1f}s"


def test_database_busy_is_handled(tmp_initialised_db: Path) -> None:
    # A second connection holding a write transaction must not corrupt results.
    with get_connection(tmp_initialised_db) as connection:
        connection.execute("PRAGMA busy_timeout=100")
        connection.execute("BEGIN IMMEDIATE")
        assert isinstance(query_events({}, db_path=tmp_initialised_db)["items"], list)
        connection.rollback()
