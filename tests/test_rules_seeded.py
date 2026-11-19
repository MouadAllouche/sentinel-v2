"""Tests for the complete seeded rule set and cross-kind example (Phase 6)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.rules.defaults import DEFAULT_RULES
from core.rules.engine import evaluate_rules
from core.rules.models import validate_rule
from storage.repositories import save_events
from storage.rules_repository import (
    get_rule,
    list_rules,
    reset_all_builtin_rules,
    reset_rule,
    seed_rules,
    set_rule_enabled,
)


def test_all_seeded_rules_validate() -> None:
    assert len(DEFAULT_RULES) == 25
    ids = [definition["id"] for definition in DEFAULT_RULES]
    assert len(set(ids)) == 25
    assert "ssh-bruteforce-by-ip" in ids
    assert "success-after-failures" in ids
    assert "new-outbound-destination" in ids
    assert "world-writable-sensitive-file" in ids
    for definition in DEFAULT_RULES:
        validate_rule(definition)


def test_seeding_idempotent_reset_and_disabled_default(tmp_initialised_db: Path) -> None:
    assert seed_rules(tmp_initialised_db)["rules"] == 25
    disabled = get_rule("new-outbound-destination", tmp_initialised_db)
    assert disabled is not None and disabled.enabled is False
    assert seed_rules(tmp_initialised_db)["rules"] == 0
    rule = get_rule("ssh-bruteforce-by-ip", tmp_initialised_db)
    assert rule is not None and rule.enabled is True
    set_rule_enabled("ssh-bruteforce-by-ip", False, "alice", tmp_initialised_db)
    seed_rules(tmp_initialised_db)
    assert get_rule("ssh-bruteforce-by-ip", tmp_initialised_db).enabled is False
    reset_rule("ssh-bruteforce-by-ip", "alice", tmp_initialised_db)
    assert get_rule("ssh-bruteforce-by-ip", tmp_initialised_db).enabled is True
    assert len(list_rules(db_path=tmp_initialised_db)) == 25


def test_disabled_default_column_and_bulk_reset(tmp_initialised_db: Path) -> None:
    seed_rules(tmp_initialised_db)
    from storage.database import get_connection

    connection = get_connection(tmp_initialised_db)
    enabled = connection.execute(
        "SELECT enabled FROM rules WHERE id = ?", ("new-outbound-destination",)
    ).fetchone()[0]
    connection.close()
    assert enabled == 0
    set_rule_enabled("ssh-bruteforce-by-ip", False, "alice", tmp_initialised_db)
    assert reset_all_builtin_rules("alice", tmp_initialised_db) == 25
    assert get_rule("ssh-bruteforce-by-ip", tmp_initialised_db).enabled is True


def test_docs_describe_every_seeded_rule() -> None:
    docs = Path(__file__).resolve().parents[1] / "docs" / "RULES.md"
    text = docs.read_text(encoding="utf-8")
    for definition in DEFAULT_RULES:
        assert definition["id"] in text


def test_cross_kind_worked_example(make_event: Callable[..., dict[str, Any]]) -> None:
    base = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)

    def event(index: int, seconds: int, **overrides: Any) -> dict[str, Any]:
        return make_event(
            id=index,
            timestamp=(base + timedelta(seconds=seconds)).isoformat(),
            source_ip=overrides.pop("source_ip", "203.0.113.45"),
            username=overrides.pop("username", "admin"),
            **overrides,
        )

    events = [event(i, i * 40, event_type="failed_login") for i in range(6)]
    events.append(event(100, 420, event_type="successful_login"))
    events.append(event(101, 540, event_type="sudo_command", process_name="visudo"))
    rules = [
        validate_rule(definition)[0]
        for definition in DEFAULT_RULES
        if definition["id"] in {"ssh-bruteforce-by-ip", "success-after-failures", "sensitive-sudo"}
    ]
    findings, warnings = evaluate_rules(rules, events, now=base + timedelta(hours=1))
    assert warnings == []
    by_rule = {item.rule_id: item.severity for item in findings}
    assert by_rule == {
        "ssh-bruteforce-by-ip": "medium",
        "success-after-failures": "high",
        "sensitive-sudo": "high",
    }
    sequence = next(item for item in findings if item.rule_id == "success-after-failures")
    assert sequence.window_start == base.isoformat()
    assert sequence.window_end == (base + timedelta(seconds=420)).isoformat()
    assert len(sequence.evidence_event_ids) == 7


def test_seeded_rule_triggered_events_are_unique(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    seed_rules(tmp_initialised_db)
    from engine.rules import run_rules

    base = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    events = [
        make_event(
            id=i,
            timestamp=(base + timedelta(seconds=i * 10)).isoformat(),
            source_ip="203.0.113.45",
            event_type="failed_login",
        )
        for i in range(6)
    ]
    save_events(events, tmp_initialised_db)
    first = run_rules(tmp_initialised_db, now=base + timedelta(seconds=60))
    second = run_rules(tmp_initialised_db, now=base + timedelta(seconds=60))
    assert first.triggered_events_new >= 1
    assert second.triggered_events_new == 0
