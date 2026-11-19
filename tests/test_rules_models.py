"""Tests for rule document validation (Phase 5)."""

from __future__ import annotations

from typing import Any

import pytest

from core.rules.models import RuleValidationError, validate_rule

BASE: dict[str, Any] = {
    "id": "ssh-bruteforce-by-ip",
    "name": "SSH brute force from one IP",
    "description": "Repeated failed logins from the same source IP",
    "kind": "threshold",
    "enabled": True,
    "match": {"event_types": ["failed_login", "invalid_user"], "conditions": {"all": []}},
    "scope": {"exclude_allowlisted": True},
    "actions": {"create_incident": True, "notify": True, "tags": ["brute-force"]},
    "mitre": ["T1110.001"],
    "group_by": ["source_ip"],
    "aggregate": {"type": "count"},
    "window_mode": "sliding",
    "cooldown_seconds": 900,
    "tiers": [
        {
            "label": "Repeated failures",
            "count": 5,
            "window_seconds": 600,
            "severity": "medium",
            "points": 15,
        },
        {
            "label": "Sustained attack",
            "count": 20,
            "window_seconds": 600,
            "severity": "high",
            "points": 30,
        },
        {"label": "Burst", "count": 50, "window_seconds": 60, "severity": "critical", "points": 45},
    ],
}


def _rule(**changes: Any) -> dict[str, Any]:
    return {**BASE, **changes}


def _tier(label: str) -> dict[str, object]:
    return {"label": label, "count": 5, "window_seconds": 600, "severity": "low", "points": 1}


def test_valid_user_example() -> None:
    rule, warnings = validate_rule(_rule())
    assert rule.id == BASE["id"]
    assert len(rule.tiers) == 3
    assert warnings == []


def test_warnings_for_dominated_tiers() -> None:
    changed = _rule(
        tiers=[
            {"label": "high", "count": 20, "window_seconds": 600, "severity": "high", "points": 20},
            {"label": "low", "count": 30, "window_seconds": 900, "severity": "low", "points": 5},
        ]
    )
    _rule_obj, warnings = validate_rule(changed)
    assert warnings


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"id": "X"}, "id"),
        ({"id": "ab"}, "id"),
        ({"name": "x"}, "name"),
        ({"name": "n" * 81}, "name"),
        ({"description": "d" * 501}, "description"),
        ({"match": {"event_types": []}}, "event_types"),
        ({"match": {"event_types": ["rule_triggered"]}}, "rule_triggered"),
        ({"match": {"event_types": ["anomaly"]}}, "anomaly"),
        (
            {"match": {"event_types": ["failed_login"], "conditions": {"field": "x", "op": "bad"}}},
            "match.conditions",
        ),
        ({"group_by": ["bogus"]}, "group_by"),
        ({"tiers": []}, "tiers"),
        ({"tiers": [_tier(f"tier-{i}") for i in range(11)]}, "tiers"),
        (
            {
                "tiers": [
                    {
                        "label": "a",
                        "count": 0,
                        "window_seconds": 600,
                        "severity": "low",
                        "points": 1,
                    }
                ]
            },
            "count",
        ),
        (
            {
                "tiers": [
                    {"label": "a", "count": 5, "window_seconds": 5, "severity": "low", "points": 1}
                ]
            },
            "window_seconds",
        ),
        (
            {
                "tiers": [
                    {
                        "label": "a",
                        "count": 5,
                        "window_seconds": 600,
                        "severity": "bogus",
                        "points": 1,
                    }
                ]
            },
            "severity",
        ),
        (
            {
                "tiers": [
                    {
                        "label": "a",
                        "count": 5,
                        "window_seconds": 600,
                        "severity": "low",
                        "points": 101,
                    }
                ]
            },
            "points",
        ),
        ({"tiers": [{**_tier("huge"), "count": 100_001}]}, "count"),
        ({"tiers": [{**_tier("long"), "window_seconds": 2_592_001}]}, "window_seconds"),
        ({"cooldown_seconds": 700_000}, "cooldown_seconds"),
        ({"window_mode": "fixed", "fixed_alignment": None}, "fixed_alignment"),
        ({"window_mode": "fixed", "fixed_alignment": "minute"}, "window_seconds"),
        ({"aggregate": {"type": "distinct_count", "field": "bogus!"}}, "field"),
        ({"aggregate": {"type": "bogus"}}, "aggregate.type"),
        ({"junk": 1}, "junk"),
    ],
)
def test_invalid_rule_paths(changes: dict[str, Any], expected: str) -> None:
    with pytest.raises(RuleValidationError) as exc:
        validate_rule(_rule(**changes))
    assert expected in str(exc.value.errors)


def test_duplicate_tier_labels_and_windows_rejected() -> None:
    duplicate_label = _rule(
        tiers=[
            {"label": "same", "count": 5, "window_seconds": 600, "severity": "low", "points": 1},
            {"label": "same", "count": 20, "window_seconds": 600, "severity": "high", "points": 2},
        ]
    )
    with pytest.raises(RuleValidationError):
        validate_rule(duplicate_label)
    duplicate_window = _rule(
        tiers=[
            {"label": "a", "count": 5, "window_seconds": 600, "severity": "low", "points": 1},
            {"label": "b", "count": 5, "window_seconds": 600, "severity": "high", "points": 2},
        ]
    )
    with pytest.raises(RuleValidationError):
        validate_rule(duplicate_window)


def test_valid_details_distinct_field() -> None:
    rule, warnings = validate_rule(
        _rule(aggregate={"type": "distinct_count", "field": "details.account"})
    )
    assert rule.aggregate.field == "details.account"
    assert warnings == []


def test_fixed_mode_valid_alignment() -> None:
    fixed = _rule(
        window_mode="fixed",
        fixed_alignment="minute",
        tiers=[
            {
                "label": "per-minute",
                "count": 5,
                "window_seconds": 60,
                "severity": "medium",
                "points": 15,
            },
        ],
    )
    rule, warnings = validate_rule(fixed)
    assert rule.window_mode == "fixed"
    assert rule.fixed_alignment == "minute"
    assert warnings == []
