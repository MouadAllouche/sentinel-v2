"""Tests for pure explainable risk scoring (Phase 10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.risk_scoring import (
    DEFAULT_THRESHOLDS,
    Decay,
    event_score,
    score_incident,
    score_severity,
    validate_thresholds,
)

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)
THRESHOLDS = dict(DEFAULT_THRESHOLDS)


def _finding(
    rule_id: str,
    points: int,
    severity: str = "medium",
    *,
    tier_label: str = "Tier",
    when: datetime | None = None,
    evidence: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "rule_version": 1,
        "rule_name": rule_id.replace("-", " ").title(),
        "tier_index": 0,
        "tier_label": tier_label,
        "severity": severity,
        "points": points,
        "window_end": (when or NOW - timedelta(minutes=5)).isoformat(),
        "evidence_event_ids": evidence or [1, 2, 3],
        "explanation": f"{points} points from {rule_id}",
    }


def _incident(**changes: Any) -> dict[str, Any]:
    incident: dict[str, Any] = {
        "id": 1,
        "status": "open",
        "event_ids": [1, 2, 3],
        "first_seen": (NOW - timedelta(minutes=10)).isoformat(),
        "last_seen": NOW.isoformat(),
        "weak_link_ratio": 0.0,
    }
    incident.update(changes)
    return incident


def _meta(
    identifier: str, metric: str, op: str, value: Any, points: int, severity: str = "medium"
) -> Any:
    from core.rules.models import validate_rule

    return validate_rule(
        {
            "id": identifier,
            "name": identifier.replace("-", " ").title(),
            "description": "Incident aggregate condition",
            "kind": "incident_meta",
            "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
            "scope": {"exclude_allowlisted": True},
            "actions": {"create_incident": False, "notify": True, "tags": []},
            "mitre": [],
            "severity": severity,
            "points": points,
            "conditions": [{"metric": metric, "op": op, "value": value}],
        }
    )[0]


def _events() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "event_type": "failed_login",
            "severity": "low",
            "timestamp": (NOW - timedelta(minutes=10)).isoformat(),
        },
        {
            "id": 2,
            "event_type": "successful_login",
            "severity": "low",
            "timestamp": (NOW - timedelta(minutes=8)).isoformat(),
        },
        {
            "id": 3,
            "event_type": "sudo_command",
            "severity": "low",
            "timestamp": (NOW - timedelta(minutes=6)).isoformat(),
        },
        {
            "id": 4,
            "event_type": "config_drift",
            "severity": "high",
            "timestamp": (NOW - timedelta(minutes=4)).isoformat(),
        },
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, "low"),
        (19, "low"),
        (20, "medium"),
        (39, "medium"),
        (40, "high"),
        (69, "high"),
        (70, "critical"),
        (100, "critical"),
    ],
)
def test_score_severity_boundaries(raw: int, expected: str) -> None:
    assert score_severity(raw, THRESHOLDS) == expected


def test_one_rule_counted_once_highest_tier() -> None:
    findings = [
        _finding("ssh-bruteforce-by-ip", 15, "medium", tier_label="Repeated failures"),
        _finding("ssh-bruteforce-by-ip", 30, "high", tier_label="Sustained attack"),
        _finding("ssh-bruteforce-by-ip", 45, "critical", tier_label="Burst"),
    ]
    assessment = score_incident(_incident(), _events(), findings, [], THRESHOLDS, now=NOW)
    assert assessment.raw_score == 45
    assert assessment.score == 45
    assert assessment.severity == "critical"  # highest tier sets the rule floor
    assert sum(reason.get("points", 0) for reason in assessment.reasons) == 45


def test_cap_and_summary() -> None:
    findings = [
        _finding("a", 40, "high"),
        _finding("b", 30, "high"),
        _finding("c", 20, "medium"),
        _finding("d", 10, "low"),
    ]
    assessment = score_incident(_incident(), _events(), findings, [], THRESHOLDS, now=NOW)
    assert assessment.raw_score == 100
    assert assessment.score == 100
    assert assessment.capped is False
    summary = next(reason for reason in assessment.reasons if reason.get("kind") == "summary")
    assert summary["raw_score"] == 100 and summary["score"] == 100


def test_rule_floor_decides_severity() -> None:
    findings = [_finding("critical-rule", 5, "critical", tier_label="Extreme")]
    assessment = score_incident(_incident(), _events(), findings, [], THRESHOLDS, now=NOW)
    assert assessment.score == 5
    assert assessment.severity == "critical"
    assert "floor" in " ".join(str(reason.get("explanation", "")) for reason in assessment.reasons)


def test_meta_rule_metrics_and_weak_link_caveat() -> None:
    meta = [
        _meta("multiple-related-events", "distinct_event_types", "gte", 3, 10),
        _meta("credential-chain", "has_event_type:successful_login", "eq", True, 15, "high"),
    ]
    assessment = score_incident(
        _incident(weak_link_ratio=0.75), _events(), [], meta, THRESHOLDS, now=NOW
    )
    assert assessment.raw_score == 25
    assert any(
        "time-proximity only" in str(reason.get("explanation", ""))
        or "caution" in str(reason.get("explanation", ""))
        for reason in assessment.reasons
    )


@pytest.mark.parametrize(
    ("metric", "op", "value", "expected"),
    [
        ("event_count", "gte", 4, True),
        ("distinct_rules_fired", "eq", 0, True),
        ("has_event_type:config_drift", "eq", True, True),
        ("span_minutes", "lte", 10, True),
        ("contains_privileged_activity", "eq", True, True),
        ("contains_persistence_change", "eq", True, True),
        ("weak_link_ratio", "gt", 0.5, False),
    ],
)
def test_meta_metrics(metric: str, op: str, value: Any, expected: bool) -> None:
    rule = _meta("meta-check", metric, op, value, 5)
    assessment = score_incident(_incident(), _events(), [], [rule], THRESHOLDS, now=NOW)
    assert (assessment.raw_score == 5) is expected


def test_decay_math_and_floor() -> None:
    findings = [_finding("old", 40, "high", when=NOW - timedelta(hours=72))]
    off = score_incident(_incident(), _events(), findings, [], THRESHOLDS, now=NOW)
    on = score_incident(
        _incident(),
        _events(),
        findings,
        [],
        THRESHOLDS,
        now=NOW,
        decay=Decay(enabled=True, half_life_hours=72),
    )
    assert off.raw_score == 40
    assert on.raw_score == pytest.approx(20.0)
    assert on.score == 20
    very_old = score_incident(
        _incident(status="resolved"),
        _events(),
        [_finding("ancient", 40, "high", when=NOW - timedelta(hours=72 * 8))],
        [],
        THRESHOLDS,
        now=NOW,
        decay=Decay(enabled=True, half_life_hours=72),
    )
    assert very_old.severity == "low"


def test_thresholds_reject_non_increasing() -> None:
    with pytest.raises(ValueError):
        validate_thresholds({"medium": 20, "high": 20, "critical": 70})
    with pytest.raises(ValueError):
        score_severity(20, {"medium": 20, "high": 10, "critical": 70})
    with pytest.raises(ValueError):
        validate_thresholds({"medium": 20, "high": 40})


def test_decay_open_incident_keeps_rule_floor() -> None:
    assessment = score_incident(
        _incident(status="open"),
        _events(),
        [_finding("ancient", 40, "high", when=NOW - timedelta(hours=72 * 8))],
        [],
        THRESHOLDS,
        now=NOW,
        decay=Decay(enabled=True, half_life_hours=72),
    )
    assert assessment.severity == "high"
    assert "open incident" in " ".join(
        str(reason.get("explanation", "")) for reason in assessment.reasons
    )


def test_event_score() -> None:
    result = event_score({"event_type": "failed_login"})
    assert result["points"] == 5
    assert result["source"] == "event_type_default"


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(points=st.lists(st.integers(min_value=0, max_value=100), min_size=1, max_size=8))
def test_reason_points_sum_to_raw_score(points: list[int]) -> None:
    findings = [_finding(f"rule-{index}", value) for index, value in enumerate(points)]
    assessment = score_incident(_incident(), _events(), findings, [], THRESHOLDS, now=NOW)
    assert sum(reason.get("points", 0) for reason in assessment.reasons) == assessment.raw_score


def test_risk_worked_example() -> None:
    findings = [
        _finding("ssh-bruteforce-by-ip", 15, "medium", tier_label="Repeated failures"),
        _finding("success-after-failures", 20, "high"),
        _finding("sensitive-sudo", 20, "high"),
        _finding("world-writable-sensitive-file", 40, "critical"),
        _finding("sensitive-file-change", 30, "high"),
    ]
    meta = [
        _meta("multiple-related-events", "distinct_event_types", "gte", 3, 10),
        _meta(
            "credential-to-privilege-chain",
            "has_event_type:successful_login",
            "eq",
            True,
            15,
            "high",
        ),
        _meta("drift-after-access", "has_event_type:config_drift", "eq", True, 20, "high"),
    ]
    assessment = score_incident(_incident(), _events(), findings, meta, THRESHOLDS, now=NOW)
    assert assessment.raw_score == 170
    assert assessment.score == 100
    assert assessment.capped is True
    assert assessment.severity == "critical"
    assert (
        len(
            {
                reason.get("rule_id")
                for reason in assessment.reasons
                if reason.get("kind") in {"rule", "meta"}
            }
        )
        == 8
    )
