"""Tests for the shared condition DSL (Phase 4)."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.conditions import describe, evaluate, validate_condition


def test_leaf_ops(make_event: Any) -> None:
    event = make_event(
        username="root",
        source_ip="203.0.113.45",
        description="Failed SSH login",
        destination_port=22,
        details={"command_executable": "/usr/bin/visudo", "flags": ["world_writable"]},
        enrichment={"ip_scope": "public"},
    )
    cases = [
        ({"field": "username", "op": "eq", "value": "root"}, True),
        ({"field": "username", "op": "eq", "value": "ROOT"}, False),
        ({"field": "username", "op": "eq", "value": "ROOT", "ci": True}, True),
        ({"field": "username", "op": "ne", "value": "bob"}, True),
        ({"field": "username", "op": "in", "value": ["root", "admin"]}, True),
        ({"field": "username", "op": "not_in", "value": ["bob"]}, True),
        ({"field": "description", "op": "contains", "value": "SSH"}, True),
        ({"field": "description", "op": "not_contains", "value": "telnet"}, True),
        ({"field": "description", "op": "startswith", "value": "Failed"}, True),
        ({"field": "description", "op": "endswith", "value": "login"}, True),
        ({"field": "description", "op": "regex", "value": r"Failed SSH \w+"}, True),
        ({"field": "destination_port", "op": "gte", "value": 22}, True),
        ({"field": "destination_port", "op": "gt", "value": 22}, False),
        ({"field": "destination_port", "op": "lte", "value": 22}, True),
        ({"field": "destination_port", "op": "lt", "value": 22}, False),
        ({"field": "username", "op": "exists"}, True),
        ({"field": "missing", "op": "not_exists"}, True),
        ({"field": "source_ip", "op": "cidr_in", "value": ["203.0.113.0/24"]}, True),
        ({"field": "source_ip", "op": "cidr_not_in", "value": ["10.0.0.0/8"]}, True),
        ({"field": "details.command_executable", "op": "eq", "value": "/usr/bin/visudo"}, True),
        ({"field": "details.flags", "op": "contains", "value": "world_writable"}, True),
        ({"field": "enrichment.ip_scope", "op": "eq", "value": "public"}, True),
    ]
    for condition, expected in cases:
        validated = validate_condition(condition)
        assert evaluate(validated, event) is expected, condition


def test_missing_field_and_invalid_ip(make_event: Any) -> None:
    event = make_event(source_ip="not-an-ip")
    assert evaluate(validate_condition({"field": "nope", "op": "eq", "value": "x"}), event) is False
    assert (
        evaluate(
            validate_condition({"field": "source_ip", "op": "cidr_in", "value": ["10.0.0.0/8"]}),
            event,
        )
        is False
    )


def test_groups_and_depth(make_event: Any) -> None:
    event = make_event(username="root", source_ip="203.0.113.45")
    all_group = {
        "all": [
            {"field": "username", "op": "eq", "value": "root"},
            {
                "any": [
                    {"field": "source_ip", "op": "eq", "value": "203.0.113.45"},
                    {"field": "source_ip", "op": "eq", "value": "198.51.100.7"},
                ]
            },
        ]
    }
    assert evaluate(validate_condition(all_group), event) is True
    negated = {"not": {"field": "username", "op": "eq", "value": "bob"}}
    assert evaluate(validate_condition(negated), event) is True
    assert validate_condition({}) is not None  # empty is always true
    assert evaluate(validate_condition({}), event) is True


def test_depth_limit_rejected() -> None:
    condition: dict[str, Any] = {"field": "username", "op": "eq", "value": "root"}
    for _ in range(5):
        condition = {"not": condition}
    with pytest.raises(ValueError, match="depth"):
        validate_condition(condition)


@pytest.mark.parametrize(
    "condition",
    [
        {"field": "username", "op": "nope", "value": "root"},
        {"field": "username", "op": "in", "value": "root"},
        {"field": "username", "op": "in", "value": ["x"] * 501},
        {"field": "username", "op": "regex", "value": "a" * 201},
        {"field": "username", "op": "regex", "value": "(a+)+"},
        {"field": "username", "op": "regex", "value": "(.*)*"},
        {"field": "username", "op": "regex", "value": "(a|aa)+"},
        {"field": "username", "op": "regex", "value": "(a+){2,}"},
        {"field": "username", "op": "regex", "value": "((a+))+"},
        {"field": "username", "op": "eq", "value": "root", "junk": 1},
    ],
)
def test_invalid_conditions_rejected(condition: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        validate_condition(condition)


def test_long_regex_field_is_bounded(make_event: Any) -> None:
    event = make_event(description="A" * 1000)
    condition = validate_condition({"field": "description", "op": "regex", "value": "A+$"})
    assert evaluate(condition, event) is True


def test_describe(make_event: Any) -> None:
    condition = validate_condition(
        {
            "all": [
                {"field": "username", "op": "eq", "value": "root"},
                {"field": "source_ip", "op": "cidr_in", "value": ["10.0.0.0/8"]},
            ]
        }
    )
    text = describe(condition)
    assert "username" in text and "AND" in text and "10.0.0.0/8" in text


_LEAVES = st.sampled_from(
    [
        {"field": "username", "op": "eq", "value": "root"},
        {"field": "source_ip", "op": "cidr_in", "value": ["10.0.0.0/8"]},
        {"field": "description", "op": "contains", "value": "x"},
        {"field": "missing", "op": "not_exists"},
    ]
)


@settings(
    max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(condition=_LEAVES, username=st.text(max_size=8))
def test_evaluate_never_raises(condition: dict[str, Any], username: str, make_event: Any) -> None:
    parsed = validate_condition(condition)
    assert isinstance(evaluate(parsed, make_event(username=username)), bool)
