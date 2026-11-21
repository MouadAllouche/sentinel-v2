"""Tests for pure baseline statistics (Phase 8)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.baseline import METRICS, BaselineSettings, compute_baseline, hourly_buckets

BASE = datetime(2026, 11, 15, 12, 30, tzinfo=UTC)


def _event(
    make_event: Callable[..., dict[str, Any]],
    identifier: int,
    when: datetime,
    **overrides: Any,
) -> dict[str, Any]:
    event = make_event(
        id=identifier,
        timestamp=when.isoformat(),
        event_type=overrides.pop("event_type", "failed_login"),
        source=overrides.pop("source", "auth_log"),
    )
    for key, value in list(overrides.items()):
        if value is None:
            del overrides[key]
    event.update(overrides)
    return event


def test_metric_catalogue() -> None:
    assert "failed_logins_per_hour" in METRICS
    assert "known_login_ips" in METRICS
    assert len(METRICS) == 7


def test_zero_filled_buckets_and_completed_hour(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [
        _event(make_event, 1, BASE.replace(minute=0, second=0) - timedelta(hours=2)),
        _event(make_event, 2, BASE.replace(minute=0, second=0) - timedelta(hours=2)),
        _event(make_event, 3, BASE.replace(minute=0, second=0)),  # current hour: excluded
    ]
    buckets = hourly_buckets(events, "failed_logins_per_hour", "global", window_days=1, now=BASE)
    assert len(buckets) == 24
    assert buckets[-2]["value"] == 2  # two hours ago
    assert buckets[-1]["value"] == 0  # last completed hour had no events


def test_last_completed_hour_counts_every_event_in_the_hour(
    make_event: Callable[..., dict[str, Any]],
) -> None:
    """The evaluated hour is [hour_start, hour_start + 1h), not a single instant."""
    hour = BASE.replace(minute=0, second=0) - timedelta(hours=1)
    events = [_event(make_event, i, hour + timedelta(minutes=i * 5)) for i in range(6)]
    buckets = hourly_buckets(events, "failed_logins_per_hour", "global", window_days=1, now=BASE)
    assert buckets[-1]["value"] == 6
    # The current partial hour is still excluded.
    events.append(_event(make_event, 99, BASE.replace(minute=0)))
    buckets = hourly_buckets(events, "failed_logins_per_hour", "global", window_days=1, now=BASE)
    assert buckets[-1]["value"] == 6


def test_exact_stats_and_maturity(make_event: Callable[..., dict[str, Any]]) -> None:
    start = BASE.replace(minute=0, second=0) - timedelta(hours=47)
    events = [
        _event(make_event, 1, start + timedelta(hours=i), event_type="successful_login")
        for i in range(48)
    ]
    events += [
        _event(
            make_event,
            100 + i,
            start + timedelta(hours=i),
            source_ip="203.0.113.45",
            event_type="failed_login",
        )
        for i in (0, 2)
    ]
    baseline = compute_baseline(
        events,
        "failed_logins_per_hour",
        "global",
        settings=BaselineSettings(window_days=2, min_samples=10, min_history_hours=24),
        now=BASE,
    )
    assert baseline.sample_count == 48
    assert baseline.maturity == "mature"
    assert abs(baseline.mean - (2 / 48)) < 1e-9


def test_exclusions(make_event: Callable[..., dict[str, Any]]) -> None:
    hour = BASE.replace(minute=0, second=0) - timedelta(hours=1)
    events = [
        _event(make_event, 1, hour),
        _event(make_event, 2, hour, source="baseline", event_type="anomaly"),
        _event(make_event, 3, hour, event_type="rule_triggered", source="rules"),
        _event(make_event, 4, hour, enrichment={"allowlist_suppressed": True}),
    ]
    buckets = hourly_buckets(events, "failed_logins_per_hour", "global", window_days=1, now=BASE)
    assert buckets[-1]["value"] == 1


def test_immature_history(make_event: Callable[..., dict[str, Any]]) -> None:
    recent = [_event(make_event, i, BASE - timedelta(hours=i)) for i in range(6)]
    baseline = compute_baseline(
        recent,
        "failed_logins_per_hour",
        "global",
        settings=BaselineSettings(window_days=1, min_samples=4, min_history_hours=24),
        now=BASE,
    )
    assert baseline.maturity == "immature"
    assert "only" in baseline.reason and "24" in baseline.reason


def test_subject_expansion_top_50_by_volume(make_event: Callable[..., dict[str, Any]]) -> None:
    from engine.baselines import subjects_for_metric

    events = [
        _event(
            make_event,
            index,
            BASE - timedelta(hours=1),
            source_ip=f"10.0.0.{index}",
            event_type="failed_login",
        )
        for index in range(60)
    ]
    events += [
        _event(
            make_event,
            1000 + index,
            BASE - timedelta(hours=2),
            source_ip="10.9.9.9",
            event_type="failed_login",
        )
        for index in range(5)
    ]
    events.append(
        _event(
            make_event,
            2000,
            BASE - timedelta(hours=2),
            source_ip="10.8.8.8",
            event_type="successful_login",
        )
    )
    subjects = subjects_for_metric("failed_logins_per_hour_by_ip", events)
    assert len(subjects) == 50
    assert subjects[0] == "10.9.9.9"
    assert "10.8.8.8" not in subjects


def test_performance_30_days_50_subjects(make_event: Callable[..., dict[str, Any]]) -> None:
    import time

    from core.baseline import BaselineSettings

    events = [
        _event(
            make_event,
            index,
            BASE - timedelta(hours=index % 720),
            source_ip=f"10.0.{index % 50}.1",
            event_type="failed_login",
        )
        for index in range(1500)
    ]
    started = time.perf_counter()
    for subject in {str(event["source_ip"]) for event in events}:
        compute_baseline(
            events,
            "failed_logins_per_hour_by_ip",
            subject,
            now=BASE,
            settings=BaselineSettings(window_days=30),
        )
    assert time.perf_counter() - started < 10


def test_hour_of_week_fallback(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [_event(make_event, i, BASE - timedelta(hours=i)) for i in range(24)]
    baseline = compute_baseline(
        events,
        "failed_logins_per_hour",
        "global",
        settings=BaselineSettings(
            window_days=7, min_samples=4, min_history_hours=24, hour_of_week=True
        ),
        now=BASE,
    )
    assert "hour-of-week" in baseline.reason or baseline.maturity == "mature"


@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(count=st.integers(min_value=0, max_value=20))
def test_baseline_never_raises(count: int, make_event: Callable[..., dict[str, Any]]) -> None:
    events = [_event(make_event, i, BASE - timedelta(hours=i % 5)) for i in range(count)]
    baseline = compute_baseline(events, "failed_logins_per_hour", "global", now=BASE)
    assert baseline.sample_count >= 0
