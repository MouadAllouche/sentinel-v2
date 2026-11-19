"""Tests for retention planning and application (Phase 11)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from core.retention import DEFAULT_POLICY, PrunePlan, plan_prune, validate_policy
from storage.repositories import get_setting, set_setting
from storage.retention_repository import apply_prune

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


def test_default_policy_and_validation() -> None:
    validate_policy(DEFAULT_POLICY)
    assert DEFAULT_POLICY["events"]["low_days"] == 14
    try:
        validate_policy({**DEFAULT_POLICY, "events": {"low_days": -1}})
    except ValueError:
        pass
    else:
        raise AssertionError("negative retention days must be rejected")


def test_plan_protects_open_incident_evidence() -> None:
    policy = dict(DEFAULT_POLICY)
    stats = {
        "events": {
            "low": 100,
            "medium": 50,
            "high": 10,
            "critical": 5,
            "linked_open": 20,
        },
        "oldest_event_days": 30,
        "baselines_needed": 7,
        "audit_days": 800,
    }
    plan = plan_prune(policy, stats, now=NOW)
    assert "linked_open" not in plan.delete_counts
    assert plan.delete_counts.get("events_low", 0) == 80
    assert plan.keep_baselines is True


def test_apply_prune_dry_run_and_audit(tmp_initialised_db: Path) -> None:
    set_setting("retention", DEFAULT_POLICY, updated_by="alice", db_path=tmp_initialised_db)
    plan = PrunePlan(delete_counts={"events_low": 1}, keep_baselines=True, vacuum=False)
    first = apply_prune(plan, tmp_initialised_db, dry_run=True, actor="alice")
    assert first["applied"] is False
    second = apply_prune(plan, tmp_initialised_db, dry_run=False, actor="alice")
    assert second["applied"] is True
    assert get_setting("retention", tmp_initialised_db) == DEFAULT_POLICY
