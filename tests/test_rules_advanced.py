"""Tests for sequence, new-value and field-match evaluators (Phase 6)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.rules.engine import evaluate_rules
from core.rules.field_match import evaluate_field_match
from core.rules.models import Rule, RuleValidationError, validate_rule
from core.rules.new_value import ValueHistory, evaluate_new_value
from core.rules.sequence import evaluate_sequence

BASE = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


def _at(
    make_event: Callable[..., dict[str, Any]], index: int, seconds: int, **overrides: Any
) -> dict[str, Any]:
    return make_event(
        id=index,
        timestamp=(BASE + timedelta(seconds=seconds)).isoformat(),
        **overrides,
    )


def _sequence(**changes: Any) -> Rule:
    definition: dict[str, Any] = {
        "id": "success-after-failures",
        "name": "Successful login after repeated failures",
        "description": "Success after failures",
        "kind": "sequence",
        "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
        "scope": {"exclude_allowlisted": True},
        "actions": {"create_incident": True, "notify": True, "tags": []},
        "mitre": ["T1110", "T1078"],
        "correlate_on": ["source_ip"],
        "within_seconds": 900,
        "steps": [
            {
                "name": "failures",
                "match": {"event_types": ["failed_login"]},
                "min_count": 5,
                "window_seconds": 600,
            },
            {"name": "success", "match": {"event_types": ["successful_login"]}, "min_count": 1},
        ],
        "severity": "high",
        "points": 20,
        "cooldown_seconds": 900,
    }
    definition.update(changes)
    return validate_rule(definition)[0]


def _new_value(**changes: Any) -> Rule:
    definition: dict[str, Any] = {
        "id": "new-ip-login",
        "name": "Login from a never-seen IP",
        "description": "First login from an IP",
        "kind": "new_value",
        "match": {"event_types": ["successful_login"], "conditions": {"all": []}},
        "scope": {"exclude_allowlisted": True},
        "actions": {"create_incident": True, "notify": True, "tags": []},
        "mitre": ["T1078"],
        "field": "source_ip",
        "per": "username",
        "learning_days": 30,
        "min_history_events": 5,
        "severity": "medium",
        "points": 10,
        "cooldown_seconds": 0,
    }
    definition.update(changes)
    return validate_rule(definition)[0]


def _field_match(**changes: Any) -> Rule:
    definition: dict[str, Any] = {
        "id": "sensitive-sudo",
        "name": "Sudo of a sensitive command",
        "description": "Sensitive sudo command",
        "kind": "field_match",
        "match": {
            "event_types": ["sudo_command"],
            "conditions": {
                "all": [
                    {
                        "field": "process_name",
                        "op": "in",
                        "value": [
                            "visudo",
                            "passwd",
                            "useradd",
                            "usermod",
                            "userdel",
                            "chmod",
                            "chown",
                            "crontab",
                        ],
                    },
                ]
            },
        },
        "scope": {"exclude_allowlisted": True},
        "actions": {"create_incident": True, "notify": True, "tags": []},
        "mitre": ["T1548.003"],
        "severity": "high",
        "points": 20,
        "cooldown_seconds": 0,
        "group_by": ["username"],
    }
    definition.update(changes)
    return validate_rule(definition)[0]


def test_sequence_ordering_and_window(make_event: Callable[..., dict[str, Any]]) -> None:
    failures = [
        _at(make_event, i, i * 60, source_ip="203.0.113.45", event_type="failed_login")
        for i in range(6)
    ]
    success = _at(make_event, 100, 420, source_ip="203.0.113.45", event_type="successful_login")
    findings = evaluate_sequence(_sequence(), failures + [success], now=BASE + timedelta(hours=1))
    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].window_start == BASE.isoformat()
    assert findings[0].window_end == (BASE + timedelta(seconds=420)).isoformat()
    assert len(findings[0].evidence_event_ids) == 7

    early_success = _at(make_event, 90, 0, source_ip="203.0.113.45", event_type="successful_login")
    assert (
        evaluate_sequence(_sequence(), [early_success] + failures, now=BASE + timedelta(hours=1))
        == []
    )
    late = _at(make_event, 200, 1300, source_ip="203.0.113.45", event_type="successful_login")
    assert evaluate_sequence(_sequence(), failures + [late], now=BASE + timedelta(hours=1)) == []


def test_sequence_spaced_steps_keep_first_step_evidence(
    make_event: Callable[..., dict[str, Any]],
) -> None:
    failures = [
        _at(make_event, i, i * 60, source_ip="203.0.113.45", event_type="failed_login")
        for i in range(5)
    ]
    success = _at(make_event, 100, 940, source_ip="203.0.113.45", event_type="successful_login")
    findings = evaluate_sequence(_sequence(), failures + [success], now=BASE + timedelta(hours=1))
    assert len(findings) == 1
    assert findings[0].window_start == BASE.isoformat()
    assert len(findings[0].evidence_event_ids) == 6


def test_sequence_cooldown_allows_later_episode(make_event: Callable[..., dict[str, Any]]) -> None:
    def sequence(offset: int, base_id: int) -> list[dict[str, Any]]:
        events = [
            _at(
                make_event,
                base_id + i,
                offset + i * 60,
                source_ip="203.0.113.45",
                event_type="failed_login",
            )
            for i in range(5)
        ]
        events.append(
            _at(
                make_event,
                base_id + 100,
                offset + 420,
                source_ip="203.0.113.45",
                event_type="successful_login",
            )
        )
        return events

    events = sequence(0, 0) + sequence(2000, 200)
    findings = evaluate_sequence(_sequence(), events, now=BASE + timedelta(hours=2))
    assert len(findings) == 2


def test_sequence_multiple_entities_independent(make_event: Callable[..., dict[str, Any]]) -> None:
    events = []
    for ip in ("10.0.0.1", "10.0.0.2"):
        events.extend(
            _at(make_event, len(events) + i, i * 60, source_ip=ip, event_type="failed_login")
            for i in range(5)
        )
        events.append(
            _at(make_event, len(events), 420, source_ip=ip, event_type="successful_login")
        )
    findings = evaluate_sequence(_sequence(), events, now=BASE + timedelta(hours=1))
    assert len(findings) == 2
    assert {item.group_key for item in findings} == {"source_ip=10.0.0.1", "source_ip=10.0.0.2"}


def test_sequence_correlate_on_username_and_three_steps(
    make_event: Callable[..., dict[str, Any]],
) -> None:
    failures = [
        _at(
            make_event,
            i,
            i * 60,
            source_ip=f"10.0.0.{i}",
            username="alice",
            event_type="failed_login",
        )
        for i in range(6)
    ]
    success = _at(
        make_event, 100, 420, source_ip="10.9.9.9", username="alice", event_type="successful_login"
    )
    by_user = _sequence(correlate_on=["username"])
    assert len(evaluate_sequence(by_user, failures + [success], now=BASE + timedelta(hours=1))) == 1
    assert evaluate_sequence(_sequence(), failures + [success], now=BASE + timedelta(hours=1)) == []

    sudo = _at(
        make_event, 200, 540, source_ip="10.0.0.1", username="alice", event_type="sudo_command"
    )
    three = _sequence(
        steps=[
            {
                "name": "failures",
                "match": {"event_types": ["failed_login"]},
                "min_count": 5,
                "window_seconds": 600,
            },
            {"name": "success", "match": {"event_types": ["successful_login"]}, "min_count": 1},
            {"name": "sudo", "match": {"event_types": ["sudo_command"]}, "min_count": 1},
        ],
        correlate_on=["username"],
    )
    findings = evaluate_sequence(three, failures + [success, sudo], now=BASE + timedelta(hours=1))
    assert len(findings) == 1
    assert findings[0].window_end == (BASE + timedelta(seconds=540)).isoformat()


def test_sequence_cooldown(make_event: Callable[..., dict[str, Any]]) -> None:
    first = [
        _at(make_event, i, i * 60, source_ip="203.0.113.45", event_type="failed_login")
        for i in range(6)
    ]
    first.append(_at(make_event, 100, 420, source_ip="203.0.113.45", event_type="successful_login"))
    second = [
        _at(make_event, 200 + i, 1000 + i * 60, source_ip="203.0.113.45", event_type="failed_login")
        for i in range(6)
    ]
    second.append(
        _at(make_event, 300, 1420, source_ip="203.0.113.45", event_type="successful_login")
    )
    findings = evaluate_sequence(_sequence(), first + second, now=BASE + timedelta(hours=1))
    assert len(findings) == 1


def test_new_value_learning_repeat_and_per_entity(
    make_event: Callable[..., dict[str, Any]],
) -> None:
    rule = _new_value()
    history = {
        "alice": ValueHistory(values={"1.1.1.1", "2.2.2.2"}, count=6),
        "bob": ValueHistory(values={"3.3.3.3"}, count=1),
    }
    known = _at(
        make_event, 0, 0, username="alice", source_ip="1.1.1.1", event_type="successful_login"
    )
    novel = _at(
        make_event, 1, 60, username="alice", source_ip="9.9.9.9", event_type="successful_login"
    )
    repeat = _at(
        make_event, 2, 120, username="alice", source_ip="9.9.9.9", event_type="successful_login"
    )
    learning = _at(
        make_event, 3, 180, username="bob", source_ip="8.8.8.8", event_type="successful_login"
    )
    findings = evaluate_new_value(
        rule, [known, novel, repeat, learning], history, now=BASE + timedelta(hours=1)
    )
    assert len(findings) == 1
    assert findings[0].group_key == "username=alice"
    assert "not seen" in findings[0].explanation


def test_new_value_history_expiry(make_event: Callable[..., dict[str, Any]]) -> None:
    rule = _new_value(learning_days=1)
    history = {"alice": ValueHistory(values={"1.1.1.1"}, count=10)}
    event = _at(
        make_event, 0, 0, username="alice", source_ip="1.1.1.1", event_type="successful_login"
    )
    # The caller supplies history already bounded by the learning window; count alone is not enough.
    assert evaluate_new_value(rule, [event], history, now=BASE + timedelta(days=2)) == []


def test_field_match_fires_cooldown_and_grouping(make_event: Callable[..., dict[str, Any]]) -> None:
    sensitive = _at(
        make_event, 0, 0, event_type="sudo_command", username="alice", process_name="visudo"
    )
    benign = _at(make_event, 1, 10, event_type="sudo_command", username="alice", process_name="ls")
    findings = evaluate_field_match(
        _field_match(), [sensitive, benign], now=BASE + timedelta(hours=1)
    )
    assert len(findings) == 1
    assert findings[0].group_key == "event=0"

    second = _at(
        make_event, 2, 20, event_type="sudo_command", username="alice", process_name="passwd"
    )
    collapsed = evaluate_field_match(
        _field_match(cooldown_seconds=900), [sensitive, second], now=BASE + timedelta(hours=1)
    )
    assert len(collapsed) == 1


def test_reserved_kinds_validate() -> None:
    baseline, warnings = validate_rule(
        {
            "id": "baseline-check",
            "name": "Baseline check",
            "description": "Reserved kind",
            "kind": "baseline_metric",
            "metric": "failed_logins_per_hour",
            "subject": "global",
            "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
            "scope": {"exclude_allowlisted": True},
            "actions": {"create_incident": False, "notify": True, "tags": []},
            "mitre": [],
            "window_days": 7,
            "min_samples": 24,
            "min_history_hours": 24,
            "tiers": [
                {
                    "label": "Elevated",
                    "z": 3.0,
                    "min_absolute": 5,
                    "severity": "medium",
                    "points": 10,
                }
            ],
            "min_std": 1.0,
            "cooldown_seconds": 3600,
        }
    )
    assert baseline.kind == "baseline_metric"
    assert warnings == []
    with pytest.raises(RuleValidationError):
        validate_rule(
            {
                "id": "bad-reserved",
                "name": "Bad reserved",
                "description": "x",
                "kind": "incident_meta",
                "metric": "nope",
                "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
                "scope": {"exclude_allowlisted": True},
                "actions": {"create_incident": True, "notify": True, "tags": []},
                "mitre": [],
            }
        )


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(seed=st.integers(min_value=0, max_value=9999))
def test_evaluators_never_raise_on_arbitrary_events(
    seed: int, make_event: Callable[..., dict[str, Any]]
) -> None:
    events = [
        make_event(
            id=index,
            timestamp=(BASE + timedelta(seconds=index * 30)).isoformat(),
            source_ip="203.0.113.45",
            username="alice",
            source_ip2=seed,
        )
        for index in range(4)
    ]
    events.append({"id": 99, "event_type": "failed_login"})  # missing timestamp
    for rule in (_sequence(), _new_value(), _field_match()):
        findings, warnings = evaluate_rules([rule], events, now=BASE + timedelta(hours=1))
        assert isinstance(findings, list)
        assert isinstance(warnings, list)
