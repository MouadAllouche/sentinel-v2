"""Tests for the pure threshold evaluator (Phase 5)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.rules.models import validate_rule
from core.rules.threshold import evaluate_threshold

BASE_TIME = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


def _event(
    make_event: Callable[..., dict[str, Any]],
    index: int,
    offset: int,
    **overrides: Any,
) -> dict[str, Any]:
    return make_event(
        id=index,
        timestamp=(BASE_TIME + timedelta(seconds=offset)).isoformat(),
        source_ip=overrides.pop("source_ip", "203.0.113.45"),
        **overrides,
    )


def _rule(**changes: Any) -> Any:
    definition: dict[str, Any] = {
        "id": "threshold-test",
        "name": "Threshold test rule",
        "description": "Test threshold",
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
    return validate_rule(definition)[0]


def test_count_boundary(make_event: Callable[..., dict[str, Any]]) -> None:
    rule = _rule()
    two = [_event(make_event, i, offset) for i, offset in enumerate([0, 10])]
    three = two + [_event(make_event, 2, 20)]
    assert evaluate_threshold(rule, two, now=BASE_TIME) == []
    findings = evaluate_threshold(rule, three, now=BASE_TIME)
    assert len(findings) == 1
    assert findings[0].observed == 3
    assert findings[0].severity == "medium"


def test_window_edge_is_exclusive(make_event: Callable[..., dict[str, Any]]) -> None:
    pair_tier = [
        {"label": "Pair", "count": 2, "window_seconds": 60, "severity": "medium", "points": 10}
    ]
    rule = _rule(tiers=pair_tier)
    events = [_event(make_event, 0, 0), _event(make_event, 1, 60)]
    assert evaluate_threshold(rule, events, now=BASE_TIME) == []


def test_unsorted_input_and_duplicate_timestamps(make_event: Callable[..., dict[str, Any]]) -> None:
    rule = _rule()
    events = [
        _event(make_event, 2, 20),
        _event(make_event, 0, 0),
        _event(make_event, 1, 0),
    ]
    findings = evaluate_threshold(rule, events, now=BASE_TIME)
    assert len(findings) == 1
    assert findings[0].evidence_event_ids == [0, 1, 2]


def test_groups_are_independent(make_event: Callable[..., dict[str, Any]]) -> None:
    rule = _rule()
    events = [
        _event(make_event, 0, 0, source_ip="10.0.0.1"),
        _event(make_event, 1, 10, source_ip="10.0.0.2"),
        _event(make_event, 2, 20, source_ip="10.0.0.1"),
        _event(make_event, 3, 30, source_ip="10.0.0.1"),
    ]
    findings = evaluate_threshold(rule, events, now=BASE_TIME)
    assert len(findings) == 1
    assert findings[0].group_key == "source_ip=10.0.0.1"


def test_missing_group_field_is_ignored(make_event: Callable[..., dict[str, Any]]) -> None:
    rule = _rule()
    events = [
        make_event(
            id=i, timestamp=(BASE_TIME + timedelta(seconds=i * 10)).isoformat(), source_ip=None
        )
        for i in range(4)
    ]
    assert evaluate_threshold(rule, events, now=BASE_TIME) == []


def test_distinct_count(make_event: Callable[..., dict[str, Any]]) -> None:
    rule = _rule(aggregate={"type": "distinct_count", "field": "username"})
    events = [
        _event(make_event, 0, 0, username="alice"),
        _event(make_event, 1, 10, username="bob"),
        _event(make_event, 2, 20, username="carol"),
        _event(make_event, 3, 30, username="carol"),
    ]
    findings = evaluate_threshold(rule, events, now=BASE_TIME)
    assert len(findings) == 1
    assert findings[0].observed == 3
    assert "distinct usernames" in findings[0].explanation


def test_sliding_vs_fixed_minute_boundary(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [
        _event(make_event, 0, 50),
        _event(make_event, 1, 70),
    ]
    pair_tier = [
        {"label": "Pair", "count": 2, "window_seconds": 60, "severity": "medium", "points": 10}
    ]
    sliding = evaluate_threshold(_rule(tiers=pair_tier), events, now=BASE_TIME)
    fixed_rule = _rule(tiers=pair_tier, window_mode="fixed", fixed_alignment="minute")
    fixed = evaluate_threshold(fixed_rule, events, now=BASE_TIME)
    assert len(sliding) == 1
    assert fixed == []


def test_escalation_ranks_by_severity_not_tier_index(
    make_event: Callable[..., dict[str, Any]],
) -> None:
    tiers = [
        {
            "label": "critical",
            "count": 2,
            "window_seconds": 60,
            "severity": "critical",
            "points": 5,
        },
        {"label": "medium", "count": 3, "window_seconds": 60, "severity": "medium", "points": 50},
    ]
    rule = _rule(tiers=tiers, cooldown_seconds=900)
    events = [_event(make_event, index, index * 10) for index in range(4)]
    findings = evaluate_threshold(rule, events, now=BASE_TIME)
    assert [item.severity for item in findings] == ["critical"]
    assert findings[0].points == 5


def test_burst_boundary_49_vs_50(make_event: Callable[..., dict[str, Any]]) -> None:
    burst_tier = [
        {"label": "Burst", "count": 50, "window_seconds": 60, "severity": "critical", "points": 45}
    ]
    rule = _rule(tiers=burst_tier)
    forty_nine = [_event(make_event, index, index) for index in range(49)]
    assert evaluate_threshold(rule, forty_nine, now=BASE_TIME) == []
    fifty = forty_nine + [_event(make_event, 49, 49)]
    assert len(evaluate_threshold(rule, fifty, now=BASE_TIME)) == 1


def test_user_example_tiers(make_event: Callable[..., dict[str, Any]]) -> None:
    rule = validate_rule(
        {
            "id": "ssh-bruteforce-by-ip",
            "name": "SSH brute force from one IP",
            "description": "Repeated failed logins from the same source IP",
            "kind": "threshold",
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
                {
                    "label": "Burst",
                    "count": 50,
                    "window_seconds": 60,
                    "severity": "critical",
                    "points": 45,
                },
            ],
        }
    )[0]
    events = [_event(make_event, i, i * 20) for i in range(20)]
    events += [_event(make_event, 100 + i, 600 + i) for i in range(30)]
    findings = evaluate_threshold(rule, events, now=BASE_TIME + timedelta(hours=1))
    assert [(item.tier_index, item.severity) for item in findings] == [(0, "medium"), (1, "high")]
    assert findings[0].window_end == "2026-11-15T10:01:20+00:00"
    assert findings[1].window_end == "2026-11-15T10:06:20+00:00"


def test_allowlisted_suppressed_events_excluded(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [
        _event(
            make_event,
            i,
            i * 10,
            enrichment={"allowlist_suppressed": i % 2 == 0},
            allowlisted=i % 2 == 0,
        )
        for i in range(4)
    ]
    assert evaluate_threshold(_rule(), events, now=BASE_TIME) == []


def test_evidence_cap_and_explanation(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [_event(make_event, i, i) for i in range(600)]
    large_tier = [
        {"label": "Many", "count": 500, "window_seconds": 600, "severity": "medium", "points": 10}
    ]
    findings = evaluate_threshold(_rule(tiers=large_tier), events, now=BASE_TIME)
    assert findings
    assert len(findings[0].evidence_event_ids) == 500
    assert findings[0].observed == 500
    assert "500 failed_login events" in findings[0].explanation
    assert "threshold:" in findings[0].explanation


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(offsets=st.lists(st.integers(min_value=0, max_value=100), min_size=3, max_size=8))
def test_findings_invariant_under_input_order(
    offsets: list[int], make_event: Callable[..., dict[str, Any]]
) -> None:
    events = [_event(make_event, i, offset) for i, offset in enumerate(offsets)]
    first = evaluate_threshold(_rule(), events, now=BASE_TIME)
    second = evaluate_threshold(_rule(), list(reversed(events)), now=BASE_TIME)
    assert sorted(item.key for item in first) == sorted(item.key for item in second)


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(count=st.integers(min_value=1, max_value=5))
def test_duplicate_event_objects_with_distinct_ids(
    count: int, make_event: Callable[..., dict[str, Any]]
) -> None:
    events = [
        make_event(id=index, timestamp=BASE_TIME.isoformat(), source_ip="203.0.113.45")
        for index in range(count)
    ]
    findings = evaluate_threshold(_rule(), events, now=BASE_TIME)
    assert len(findings) == (1 if count >= 3 else 0)
