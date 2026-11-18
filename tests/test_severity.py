"""Tests for severity defaults, overrides and resolution (Phase 4)."""

from __future__ import annotations

from typing import Any

import pytest

from core.conditions import validate_condition
from core.events import EVENT_TYPES
from core.severity import (
    DEFAULT_OVERRIDES,
    DEFAULT_TYPE_DEFAULTS,
    Override,
    TypeDefault,
    resolve_severity,
    validate_defaults,
    validate_overrides,
)


def test_defaults_table_complete() -> None:
    assert set(DEFAULT_TYPE_DEFAULTS) == set(EVENT_TYPES)
    assert DEFAULT_TYPE_DEFAULTS["failed_login"].severity == "low"
    assert DEFAULT_TYPE_DEFAULTS["failed_login"].points == 5
    assert DEFAULT_TYPE_DEFAULTS["suspicious_process"].severity == "high"
    assert DEFAULT_TYPE_DEFAULTS["suspicious_process"].points == 15
    assert DEFAULT_TYPE_DEFAULTS["rule_triggered"].points == 0
    assert all(item.default_severity is not None for item in DEFAULT_TYPE_DEFAULTS.values())


def test_seeded_overrides() -> None:
    ids = [item.id for item in DEFAULT_OVERRIDES]
    assert "failed_login-root" in ids
    assert "sudo-sensitive-command" in ids
    assert "drift-world-writable" in ids
    assert "success-from-public-ip" in ids
    assert "listening-all-interfaces" in ids
    assert "listening-loopback" in ids
    assert len({item.priority for item in DEFAULT_OVERRIDES}) == len(DEFAULT_OVERRIDES)
    assert all(item.builtin for item in DEFAULT_OVERRIDES)


def test_worked_example(make_event: Any) -> None:
    defaults = dict(DEFAULT_TYPE_DEFAULTS)
    defaults["failed_login"] = TypeDefault(
        event_type="failed_login",
        severity="medium",
        points=5,
        default_severity="low",
        default_points=5,
    )
    overrides = [
        Override(
            id="failed_login-root",
            name="Failed login for root",
            priority=1,
            conditions=validate_condition(
                {
                    "all": [
                        {"field": "event_type", "op": "eq", "value": "failed_login"},
                        {"field": "username", "op": "eq", "value": "root"},
                    ]
                }
            ),
            severity="high",
        )
    ]
    assert resolve_severity(make_event(username="root"), defaults, overrides) == (
        "high",
        "override:failed_login-root",
    )
    assert resolve_severity(make_event(username="bob"), defaults, overrides) == (
        "medium",
        "default",
    )


def test_precedence_disabled_and_fallback(make_event: Any) -> None:
    first = Override(
        id="first",
        name="First",
        priority=1,
        conditions=validate_condition({"field": "event_type", "op": "eq", "value": "failed_login"}),
        severity="high",
    )
    second = Override(
        id="second",
        name="Second",
        priority=2,
        conditions=validate_condition({"field": "event_type", "op": "eq", "value": "failed_login"}),
        severity="critical",
    )
    disabled = Override(
        id="first",
        name="First",
        priority=1,
        enabled=False,
        conditions=validate_condition({"field": "event_type", "op": "eq", "value": "failed_login"}),
        severity="high",
    )
    assert resolve_severity(make_event(), DEFAULT_TYPE_DEFAULTS, [first, second]) == (
        "high",
        "override:first",
    )
    assert resolve_severity(make_event(), DEFAULT_TYPE_DEFAULTS, [disabled, second]) == (
        "critical",
        "override:second",
    )
    assert resolve_severity(make_event(event_type="unknown_type"), DEFAULT_TYPE_DEFAULTS, []) == (
        "low",
        "default",
    )


def test_drift_override_uses_dotted_path(make_event: Any) -> None:
    event = make_event(
        event_type="config_drift",
        details={"flags": ["world_writable"], "sensitivity": "high"},
    )
    severity, source = resolve_severity(event, DEFAULT_TYPE_DEFAULTS, DEFAULT_OVERRIDES)
    assert severity == "critical"
    assert source == "override:drift-world-writable"


def test_validations() -> None:
    validate_defaults(DEFAULT_TYPE_DEFAULTS)
    validate_overrides(DEFAULT_OVERRIDES)
    bad_defaults = dict(DEFAULT_TYPE_DEFAULTS)
    bad_defaults["failed_login"] = TypeDefault(
        event_type="failed_login", severity="bogus", points=5
    )
    with pytest.raises(ValueError):
        validate_defaults(bad_defaults)
    duplicate = [
        Override(id="a", name="A", priority=1, conditions=validate_condition({}), severity="low"),
        Override(id="b", name="B", priority=1, conditions=validate_condition({}), severity="low"),
    ]
    with pytest.raises(ValueError, match="unique"):
        validate_overrides(duplicate)
    with pytest.raises(ValueError, match="200"):
        validate_overrides(
            [
                Override(
                    id=str(i),
                    name=str(i),
                    priority=i,
                    conditions=validate_condition({}),
                    severity="low",
                )
                for i in range(201)
            ]
        )
