"""Tests for rule persistence and lifecycle (Phase 5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.rules.models import validate_rule
from core.rules.threshold import Finding
from storage.database import get_connection
from storage.rules_repository import (
    create_rule,
    delete_rule,
    get_rule,
    get_rule_versions,
    list_findings,
    list_rules,
    reset_rule,
    save_findings,
    seed_rules,
    set_rule_enabled,
    update_rule,
)


def _definition(**changes: object) -> dict[str, object]:
    definition: dict[str, object] = {
        "id": "custom-rule",
        "name": "Custom rule",
        "description": "A custom threshold rule",
        "kind": "threshold",
        "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
        "scope": {"exclude_allowlisted": True},
        "actions": {"create_incident": True, "notify": True, "tags": []},
        "mitre": [],
        "group_by": ["source_ip"],
        "aggregate": {"type": "count"},
        "window_mode": "sliding",
        "cooldown_seconds": 0,
        "tiers": [
            {"label": "Low", "count": 3, "window_seconds": 60, "severity": "medium", "points": 10},
        ],
    }
    definition.update(changes)
    return definition


def _audit_count(db: Path) -> int:
    connection = get_connection(db)
    total = connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    connection.close()
    return int(total)


def _finding(**changes: object) -> Finding:
    values: dict[str, object] = {
        "rule_id": "custom-rule",
        "rule_version": 1,
        "group_key": "source_ip=10.0.0.1",
        "tier_index": 0,
        "tier_label": "Low",
        "severity": "medium",
        "points": 10,
        "window_start": "2026-11-15T10:00:00+00:00",
        "window_end": "2026-11-15T10:00:30+00:00",
        "observed": 3,
        "threshold": 3,
        "window_seconds": 60,
        "evidence_event_ids": [1, 2, 3],
        "explanation": "3 failed_login events from source_ip=10.0.0.1 within 60s",
    }
    values.update(changes)
    return Finding(**values)  # type: ignore[arg-type]


def test_seed_rules_idempotent_and_reset(tmp_initialised_db: Path) -> None:
    first = seed_rules(tmp_initialised_db)
    assert first["rules"] >= 1
    before = _audit_count(tmp_initialised_db)
    assert seed_rules(tmp_initialised_db)["rules"] == 0
    builtin = next(rule for rule in list_rules(db_path=tmp_initialised_db) if rule.builtin)
    update_rule(
        builtin.id, _definition(id=builtin.id, name="Changed name"), "alice", tmp_initialised_db
    )
    seed_rules(tmp_initialised_db)
    assert get_rule(builtin.id, tmp_initialised_db).name == "Changed name"
    assert _audit_count(tmp_initialised_db) > before
    reset_rule(builtin.id, "alice", tmp_initialised_db)
    assert get_rule(builtin.id, tmp_initialised_db).version == builtin.version + 2


def test_version_bump_and_audit(tmp_initialised_db: Path) -> None:
    create_rule(_definition(), "alice", tmp_initialised_db)
    assert get_rule("custom-rule", tmp_initialised_db).version == 1
    update_rule(
        "custom-rule",
        _definition(
            tiers=[
                {
                    "label": "Low",
                    "count": 5,
                    "window_seconds": 60,
                    "severity": "medium",
                    "points": 10,
                },
            ]
        ),
        "alice",
        tmp_initialised_db,
    )
    assert get_rule("custom-rule", tmp_initialised_db).version == 2
    assert [item["version"] for item in get_rule_versions("custom-rule", tmp_initialised_db)] == [
        1,
        2,
    ]
    assert _audit_count(tmp_initialised_db) == 2


def test_enable_disable_and_soft_delete(tmp_initialised_db: Path) -> None:
    create_rule(_definition(), "alice", tmp_initialised_db)
    set_rule_enabled("custom-rule", False, "alice", tmp_initialised_db)
    assert get_rule("custom-rule", tmp_initialised_db).enabled is False
    delete_rule("custom-rule", "alice", tmp_initialised_db)
    assert get_rule("custom-rule", tmp_initialised_db) is None
    assert "custom-rule" not in {rule.id for rule in list_rules(db_path=tmp_initialised_db)}
    builtin_id = seed_rules(tmp_initialised_db) and list_rules(db_path=tmp_initialised_db)[0].id
    with pytest.raises(ValueError, match="built-in"):
        delete_rule(builtin_id, "alice", tmp_initialised_db)


def test_findings_unique_and_re_runs_idempotent(tmp_initialised_db: Path) -> None:
    create_rule(_definition(), "alice", tmp_initialised_db)
    first = save_findings([_finding()], tmp_initialised_db)
    assert first[0][1] is True
    second = save_findings([_finding()], tmp_initialised_db)
    assert second[0][1] is False
    assert len(list_findings({}, db_path=tmp_initialised_db)) == 1
    other = _finding(group_key="source_ip=10.0.0.2")
    assert save_findings([other], tmp_initialised_db)[0][1] is True
    assert len(list_findings({}, db_path=tmp_initialised_db)) == 2


def test_rule_validation_error_has_paths(tmp_initialised_db: Path) -> None:
    with pytest.raises(ValueError):
        validate_rule(_definition(tiers=[]))
