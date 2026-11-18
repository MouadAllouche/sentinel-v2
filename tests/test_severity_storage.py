"""Tests for seeded severity configuration, allowlist persistence and re-apply (Phase 4)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from core.normalizer import compute_event_hash
from core.severity import DEFAULT_OVERRIDES, DEFAULT_TYPE_DEFAULTS
from storage.database import get_connection
from storage.repositories import count_events, save_event, save_events
from storage.severity_repository import (
    add_allowlist_entry,
    create_override,
    delete_allowlist_entry,
    delete_override,
    get_allowlist_entries,
    get_default,
    get_overrides,
    reapply_severity,
    reset_all_defaults,
    reset_default,
    reset_override,
    seed_defaults,
    set_default,
    update_allowlist_entry,
    update_override,
)


def _audit_count(db: Path) -> int:
    connection = get_connection(db)
    total = connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    connection.close()
    return int(total)


def test_seeding_is_idempotent_and_preserves_edits(tmp_initialised_db: Path) -> None:
    first = seed_defaults(tmp_initialised_db)
    assert first["event_type_defaults"] == len(DEFAULT_TYPE_DEFAULTS)
    assert first["severity_overrides"] == len(DEFAULT_OVERRIDES)
    before = _audit_count(tmp_initialised_db)
    assert seed_defaults(tmp_initialised_db) == {"event_type_defaults": 0, "severity_overrides": 0}
    set_default("failed_login", "medium", 7, actor="alice", db_path=tmp_initialised_db)
    seed_defaults(tmp_initialised_db)
    assert get_default("failed_login", tmp_initialised_db).severity == "medium"
    assert _audit_count(tmp_initialised_db) > before


def test_default_edit_reset_and_audit(tmp_initialised_db: Path) -> None:
    seed_defaults(tmp_initialised_db)
    set_default("failed_login", "high", 9, actor="alice", db_path=tmp_initialised_db)
    current = get_default("failed_login", tmp_initialised_db)
    assert (current.severity, current.points, current.default_severity) == ("high", 9, "low")
    reset_default("failed_login", "alice", tmp_initialised_db)
    assert get_default("failed_login", tmp_initialised_db).severity == "low"
    set_default("failed_login", "critical", 1, actor="alice", db_path=tmp_initialised_db)
    reset_all_defaults("alice", tmp_initialised_db)
    assert get_default("failed_login", tmp_initialised_db).severity == "low"
    assert _audit_count(tmp_initialised_db) >= 4


def test_override_crud_and_ordering(tmp_initialised_db: Path) -> None:
    seed_defaults(tmp_initialised_db)
    identifier = create_override(
        {
            "name": "Test override",
            "priority": 999,
            "conditions": {"field": "username", "op": "eq", "value": "root"},
            "severity": "critical",
        },
        "alice",
        tmp_initialised_db,
    )
    overrides = get_overrides(tmp_initialised_db)
    assert [item.priority for item in overrides] == sorted(item.priority for item in overrides)
    assert identifier in {item.id for item in overrides}
    update_override(identifier, {"severity": "high"}, "alice", tmp_initialised_db)
    assert (
        next(item for item in get_overrides(tmp_initialised_db) if item.id == identifier).severity
        == "high"
    )
    reset_override(identifier, "alice", tmp_initialised_db)
    delete_override(identifier, "alice", tmp_initialised_db)
    assert identifier not in {item.id for item in get_overrides(tmp_initialised_db)}
    assert _audit_count(tmp_initialised_db) >= 4


def test_override_duplicate_priority_rejected(tmp_initialised_db: Path) -> None:
    seed_defaults(tmp_initialised_db)
    with pytest.raises(ValueError, match="unique|already"):
        create_override(
            {
                "name": "Clash",
                "priority": 1,
                "conditions": {"field": "username", "op": "eq", "value": "root"},
                "severity": "low",
            },
            "alice",
            tmp_initialised_db,
        )


def test_reapply_large_batch_is_one_transaction(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    seed_defaults(tmp_initialised_db)
    save_events(
        [make_event(description=f"batch-{index}") for index in range(60)], tmp_initialised_db
    )
    set_default("failed_login", "high", 5, actor="alice", db_path=tmp_initialised_db)
    result = reapply_severity({}, tmp_initialised_db, dry_run=False)
    assert result["examined"] >= 60
    assert result["changed"] >= 60
    assert count_events({"severity": ["high"]}, tmp_initialised_db) >= 60


def test_allowlist_crud(tmp_initialised_db: Path) -> None:
    identifier = add_allowlist_entry(
        {
            "kind": "ip",
            "value": "203.0.113.45",
            "scope": "suppress_alerts",
            "reason": "trusted scanner",
        },
        "alice",
        tmp_initialised_db,
    )
    assert any(entry.id == identifier for entry in get_allowlist_entries(tmp_initialised_db))
    with pytest.raises(ValueError, match="reason"):
        add_allowlist_entry(
            {"kind": "ip", "value": "1.2.3.4", "scope": "annotate", "reason": "x"},
            "alice",
            tmp_initialised_db,
        )
    update_allowlist_entry(identifier, {"reason": "revised reason"}, "alice", tmp_initialised_db)
    delete_allowlist_entry(identifier, "alice", tmp_initialised_db)
    assert not any(entry.id == identifier for entry in get_allowlist_entries(tmp_initialised_db))
    assert _audit_count(tmp_initialised_db) >= 3


def test_reapply_dry_run_then_real(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    seed_defaults(tmp_initialised_db)
    identifier = save_event(make_event(description="reapply target"), tmp_initialised_db)
    assert identifier is not None
    connection = get_connection(tmp_initialised_db)
    before_hash = connection.execute(
        "SELECT event_hash FROM events WHERE id = ?", (identifier,)
    ).fetchone()[0]
    connection.close()

    set_default("failed_login", "high", 5, actor="alice", db_path=tmp_initialised_db)
    dry = reapply_severity({}, tmp_initialised_db, dry_run=True)
    assert dry["changed"] >= 1
    connection = get_connection(tmp_initialised_db)
    assert (
        connection.execute("SELECT severity FROM events WHERE id = ?", (identifier,)).fetchone()[0]
        == "low"
    )
    connection.close()

    applied = reapply_severity({"event_type": ["failed_login"]}, tmp_initialised_db, dry_run=False)
    assert applied["changed"] >= 1
    connection = get_connection(tmp_initialised_db)
    row = connection.execute(
        "SELECT severity, severity_source, event_hash FROM events WHERE id = ?", (identifier,)
    ).fetchone()
    connection.close()
    assert row["severity"] == "high"
    assert row["event_hash"] == before_hash
    assert compute_event_hash(make_event(description="reapply target")) == before_hash
