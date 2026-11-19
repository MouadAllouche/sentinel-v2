"""Tests for drift storage, baseline approval and the check cycle (Phase 9)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from engine.drift import accept_baseline, baseline_status_for, check_drift, init_drift
from storage.database import get_connection
from storage.drift_repository import (
    add_monitored_path,
    get_baseline_snapshot,
    get_previous_snapshot,
    list_monitored_paths,
    reset_monitored_path,
    seed_monitored_paths,
)
from storage.repositories import query_events


def test_seed_paths_shadow_forced_metadata_only(tmp_initialised_db: Path) -> None:
    assert seed_monitored_paths(tmp_initialised_db)["monitored_paths"] >= 15
    assert seed_monitored_paths(tmp_initialised_db)["monitored_paths"] == 0
    shadow = next(
        path for path in list_monitored_paths(tmp_initialised_db) if path.path == "/etc/shadow"
    )
    assert shadow.metadata_only is True
    assert shadow.sensitivity == "critical"


def test_init_check_and_reported_once(tmp_initialised_db: Path, tmp_path: Path) -> None:
    target = tmp_path / "sample.conf"
    target.write_text("original\n")
    add_monitored_path(
        {"path": str(target), "kind": "file", "sensitivity": "high", "category": "ssh"},
        "alice",
        tmp_initialised_db,
        allow_custom_paths=True,
    )
    first = init_drift(tmp_initialised_db, now=datetime(2026, 11, 15, 10, tzinfo=UTC))
    assert first.baselines >= 1
    assert query_events({"event_type": ["config_drift"]}, db_path=tmp_initialised_db)["items"] == []
    check_drift(tmp_initialised_db, now=datetime(2026, 11, 15, 11, tzinfo=UTC))
    assert query_events({"event_type": ["config_drift"]}, db_path=tmp_initialised_db)["items"] == []

    target.write_text("changed\n")
    check_drift(tmp_initialised_db, now=datetime(2026, 11, 15, 12, tzinfo=UTC))
    events = query_events({"event_type": ["config_drift"]}, db_path=tmp_initialised_db)["items"]
    assert len(events) == 1
    assert events[0]["file_path"] == str(target)
    assert "sha256" in events[0]["details"]["changed_fields"]

    check_drift(tmp_initialised_db, now=datetime(2026, 11, 15, 13, tzinfo=UTC))
    assert (
        len(query_events({"event_type": ["config_drift"]}, db_path=tmp_initialised_db)["items"])
        == 1
    )
    assert get_previous_snapshot(str(target), tmp_initialised_db) is not None


def test_accept_baseline_and_world_writable(tmp_initialised_db: Path, tmp_path: Path) -> None:
    target = tmp_path / "sshd_config"
    target.write_text(" PermitRootLogin no\n")
    target.chmod(0o644)
    path_id = add_monitored_path(
        {"path": str(target), "kind": "file", "sensitivity": "high", "category": "ssh"},
        "alice",
        tmp_initialised_db,
        allow_custom_paths=True,
    )
    init_drift(tmp_initialised_db, now=datetime(2026, 11, 15, 10, tzinfo=UTC))
    target.chmod(0o777)
    check_drift(tmp_initialised_db, now=datetime(2026, 11, 15, 11, tzinfo=UTC))
    events = query_events({"event_type": ["config_drift"]}, db_path=tmp_initialised_db)["items"]
    assert len(events) == 1
    assert "world_writable" in events[0]["details"]["flags"]
    assert "permissions changed from 0644 to 0777" in events[0]["description"]
    assert events[0]["severity"] == "critical"

    accept_baseline(path_id, "alice", "approved change", tmp_initialised_db)
    assert get_baseline_snapshot(str(target), tmp_initialised_db) is not None
    connection = get_connection(tmp_initialised_db)
    count = connection.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = 'drift.baseline_accepted'"
    ).fetchone()[0]
    connection.close()
    assert count == 1
    check_drift(tmp_initialised_db, now=datetime(2026, 11, 15, 12, tzinfo=UTC))
    assert (
        len(query_events({"event_type": ["config_drift"]}, db_path=tmp_initialised_db)["items"])
        == 1
    )


def test_shadow_forced_metadata_only_on_add(tmp_initialised_db: Path) -> None:
    seed_monitored_paths(tmp_initialised_db)
    with get_connection(tmp_initialised_db) as connection:
        connection.execute(
            "UPDATE monitored_paths SET metadata_only = 0 WHERE path = '/etc/shadow'"
        )
    identifier = next(
        path.id for path in list_monitored_paths(tmp_initialised_db) if path.path == "/etc/shadow"
    )
    reset_monitored_path(identifier, "alice", tmp_initialised_db)
    assert (
        next(
            path for path in list_monitored_paths(tmp_initialised_db) if path.id == identifier
        ).metadata_only
        is True
    )


def test_reset_monitored_path(tmp_initialised_db: Path) -> None:
    seed_monitored_paths(tmp_initialised_db)
    identifier = next(
        path.id for path in list_monitored_paths(tmp_initialised_db) if path.path == "/etc/passwd"
    )
    with get_connection(tmp_initialised_db) as connection:
        connection.execute(
            "UPDATE monitored_paths SET sensitivity = 'low' WHERE id = ?", (identifier,)
        )
    reset_monitored_path(identifier, "alice", tmp_initialised_db)
    assert (
        next(
            path for path in list_monitored_paths(tmp_initialised_db) if path.id == identifier
        ).sensitivity
        == "high"
    )


def test_baseline_status_transitions(tmp_initialised_db: Path, tmp_path: Path) -> None:
    target = tmp_path / "status.conf"
    target.write_text("one\n")
    target.chmod(0o644)
    identifier = add_monitored_path(
        {"path": str(target), "kind": "file", "sensitivity": "low", "category": "other"},
        "alice",
        tmp_initialised_db,
        allow_custom_paths=True,
    )
    init_drift(tmp_initialised_db, now=datetime(2026, 11, 15, 10, tzinfo=UTC))
    assert baseline_status_for(identifier, tmp_initialised_db) == "clean"
    target.write_text("two\n")
    check_drift(tmp_initialised_db, now=datetime(2026, 11, 15, 11, tzinfo=UTC))
    assert baseline_status_for(identifier, tmp_initialised_db) == "drifted"
    accept_baseline(identifier, "alice", "approved", tmp_initialised_db)
    assert baseline_status_for(identifier, tmp_initialised_db) == "clean"


def test_init_refuses_overwrite(tmp_initialised_db: Path, tmp_path: Path) -> None:
    target = tmp_path / "file"
    target.write_text("data")
    add_monitored_path(
        {"path": str(target), "kind": "file", "sensitivity": "low", "category": "other"},
        "alice",
        tmp_initialised_db,
        allow_custom_paths=True,
    )
    init_drift(tmp_initialised_db)
    assert init_drift(tmp_initialised_db).baselines == 0
