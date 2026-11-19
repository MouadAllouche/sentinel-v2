"""Tests for explained anomaly detection (Phase 8)."""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.anomaly_detection import AnomalyResult, detect_anomaly
from core.baseline import Baseline
from core.normalizer import compute_event_hash
from core.rules.models import validate_rule

RULE = validate_rule(
    {
        "id": "baseline-failed-logins",
        "name": "Failed logins above normal",
        "description": "Unusual number of failed logins",
        "kind": "baseline_metric",
        "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
        "metric": "failed_logins_per_hour",
        "subject": "global",
        "window_days": 7,
        "min_samples": 24,
        "min_history_hours": 24,
        "tiers": [
            {"label": "Elevated", "z": 3.0, "min_absolute": 5, "severity": "medium", "points": 10},
            {"label": "Extreme", "z": 6.0, "min_absolute": 20, "severity": "high", "points": 20},
        ],
        "min_std": 1.0,
        "cooldown_seconds": 3600,
        "actions": {"create_incident": False, "notify": True, "tags": []},
        "mitre": ["T1110"],
    }
)[0]

HOUR = datetime(2026, 11, 15, 11, tzinfo=UTC)


def _baseline(
    mean: float = 2.0, stddev: float = 1.1, *, mature: bool = True, samples: int = 168
) -> Baseline:
    return Baseline(
        metric="failed_logins_per_hour",
        subject="global",
        window_start="2026-11-08T12:00:00+00:00",
        window_end="2026-11-15T11:00:00+00:00",
        mean=mean,
        stddev=stddev,
        sample_count=samples,
        maximum=3.0,
        p95=3.0,
        maturity="mature" if mature else "immature",
        reason="" if mature else "only 6 hours of history; need 24",
    )


def test_worked_example() -> None:
    result = detect_anomaly(
        RULE, _baseline(), observed=25, hour_start=HOUR, now=datetime(2026, 11, 15, 12, tzinfo=UTC)
    )
    assert result.status == "anomaly"
    assert result.event is not None
    assert result.event["severity"] == "high"
    assert result.event["severity_source"] == "rule:baseline-failed-logins"
    assert "20.9 standard deviations" in result.event["description"]
    assert "unusual, not necessarily malicious" in result.event["description"]
    assert result.finding is not None
    assert result.finding.tier_label == "Extreme"
    assert result.finding.points == 20


def test_immature_no_event() -> None:
    result = detect_anomaly(
        RULE,
        _baseline(mature=False),
        observed=25,
        hour_start=HOUR,
        now=datetime(2026, 11, 15, 12, tzinfo=UTC),
    )
    assert result.status == "insufficient_baseline"
    assert result.event is None
    assert result.finding is None
    assert "24" in result.reason


def test_min_std_floor_and_inclusive_comparison() -> None:
    result = detect_anomaly(
        RULE,
        _baseline(stddev=0.0),
        observed=5,
        hour_start=HOUR,
        now=datetime(2026, 11, 15, 12, tzinfo=UTC),
    )
    assert result.status == "normal"  # threshold = 2 + 3*1.0 = 5, need x > 5
    result2 = detect_anomaly(
        RULE,
        _baseline(stddev=0.0),
        observed=6,
        hour_start=HOUR,
        now=datetime(2026, 11, 15, 12, tzinfo=UTC),
    )
    assert result2.status == "anomaly"


def test_min_absolute_floor() -> None:
    result = detect_anomaly(
        RULE,
        _baseline(mean=0.0, stddev=0.1),
        observed=4,
        hour_start=HOUR,
        now=datetime(2026, 11, 15, 12, tzinfo=UTC),
    )
    assert result.status == "normal"


def test_deterministic_event_hash_and_finding_key() -> None:
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    first = detect_anomaly(RULE, _baseline(), observed=25, hour_start=HOUR, now=now)
    second = detect_anomaly(RULE, _baseline(), observed=25, hour_start=HOUR, now=now)
    later = detect_anomaly(
        RULE,
        _baseline(),
        observed=25,
        hour_start=datetime(2026, 11, 15, 12, tzinfo=UTC),
        now=now,
    )
    assert first.event and second.event
    assert compute_event_hash(first.event) == compute_event_hash(second.event)
    assert first.finding and second.finding and first.finding.key == second.finding.key
    assert later.event and compute_event_hash(first.event) != compute_event_hash(later.event)


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    observed=st.integers(min_value=0, max_value=1000), stddev=st.floats(min_value=0, max_value=50)
)
def test_detection_never_raises(observed: int, stddev: float) -> None:
    result: AnomalyResult = detect_anomaly(
        RULE,
        _baseline(stddev=stddev),
        observed=observed,
        hour_start=HOUR,
        now=datetime(2026, 11, 15, 12, tzinfo=UTC),
    )
    assert result.status in {"anomaly", "normal", "insufficient_baseline"}
