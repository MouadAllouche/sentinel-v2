"""Boundary and property audit of every time-window calculation in core/ (Phase 19).

Each window is checked at its exact edges, with fractional seconds, across
midnight, and against the current (partial) period. Properties use Hypothesis
so a future "only count the hour start" regression cannot pass by accident.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.baseline import hourly_buckets
from core.correlation import CorrelationSettings, correlate
from core.normalizer import compute_event_hash
from core.retention import DEFAULT_POLICY
from core.rules.models import validate_rule
from core.rules.threshold import evaluate_threshold
from storage.repositories import save_events
from storage.retention_repository import retention_stats

NOW = datetime(2026, 11, 21, 12, 34, 56, 789012, tzinfo=UTC)
HOUR = NOW.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)


def _event(
    make_event: Callable[..., dict[str, Any]],
    identifier: int,
    stamp: datetime,
    **overrides: Any,
) -> dict[str, Any]:
    event = make_event(id=identifier, timestamp=stamp.isoformat(), **overrides)
    return event


# --- hourly_buckets -------------------------------------------------------


def test_hourly_buckets_counts_all_instant_boundaries(make_event: Callable[..., Any]) -> None:
    events = [
        _event(make_event, 1, HOUR),
        _event(make_event, 2, HOUR + timedelta(minutes=30)),
        _event(make_event, 3, HOUR + timedelta(minutes=59, seconds=59, microseconds=999999)),
        # Previous hour and current partial hour must not enter the last bucket.
        _event(make_event, 4, HOUR - timedelta(microseconds=1)),
        _event(make_event, 5, HOUR + timedelta(hours=1)),
    ]
    buckets = hourly_buckets(events, "failed_logins_per_hour", "global", window_days=1, now=NOW)
    assert len(buckets) == 24
    assert buckets[-1]["value"] == 3
    assert buckets[-2]["timestamp"] == (HOUR - timedelta(hours=1)).isoformat()


def test_hourly_buckets_across_midnight(make_event: Callable[..., Any]) -> None:
    now = NOW.replace(hour=0, minute=30)
    hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    events = [
        _event(make_event, 1, hour),
        _event(make_event, 2, hour + timedelta(hours=1) - timedelta(microseconds=1)),
        _event(make_event, 3, now),
    ]
    buckets = hourly_buckets(events, "failed_logins_per_hour", "global", window_days=1, now=now)
    assert buckets[-1]["timestamp"] == hour.isoformat()
    assert buckets[-1]["value"] == 2


def test_hourly_buckets_exclusion_rules(make_event: Callable[..., Any]) -> None:
    events = [
        _event(make_event, 1, HOUR),
        _event(make_event, 2, HOUR, source="baseline", event_type="anomaly"),
        _event(make_event, 3, HOUR, event_type="rule_triggered", source="rules"),
        _event(make_event, 4, HOUR, enrichment={"allowlist_suppressed": True}),
        _event(make_event, 5, HOUR, event_type="successful_login"),
    ]
    buckets = hourly_buckets(events, "failed_logins_per_hour", "global", window_days=1, now=NOW)
    assert buckets[-1]["value"] == 1


@settings(
    max_examples=120,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    offsets=st.lists(
        st.one_of(
            st.integers(min_value=0, max_value=167 * 3600 + 3599),
            st.floats(min_value=0, max_value=167 * 3600 + 3599, allow_nan=False),
        ),
        min_size=0,
        max_size=40,
    )
)
def test_hourly_buckets_property_count_and_sum(
    make_event: Callable[..., Any], offsets: list
) -> None:
    events = [
        _event(make_event, index, HOUR - timedelta(hours=167) + timedelta(seconds=float(value)))
        for index, value in enumerate(offsets)
    ]
    buckets = hourly_buckets(events, "failed_logins_per_hour", "global", window_days=7, now=NOW)
    assert len(buckets) == 7 * 24  # zero-filled, including empty hours
    assert sum(item["value"] for item in buckets) == len(events)


# --- threshold sliding / fixed windows -----------------------------------


def _rule(**changes: Any) -> Any:
    definition: dict[str, Any] = {
        "id": "window-audit",
        "name": "Window audit",
        "description": "Audit window edges",
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
            {"label": "Pair", "count": 2, "window_seconds": 60, "severity": "medium", "points": 10}
        ],
    }
    definition.update(changes)
    return validate_rule(definition)[0]


def test_sliding_window_edges(make_event: Callable[..., Any]) -> None:
    base = NOW.replace(microsecond=0)
    at_start = _event(make_event, 1, base - timedelta(seconds=60), source_ip="203.0.113.45")
    inside = _event(make_event, 2, base - timedelta(seconds=59), source_ip="203.0.113.45")
    at_end = _event(make_event, 3, base, source_ip="203.0.113.45")
    # (start, end]: the event exactly at start is excluded, the end included.
    assert evaluate_threshold(_rule(), [at_start, at_end], now=base) == []
    findings = evaluate_threshold(_rule(), [inside, at_start, at_end], now=base)
    assert len(findings) == 1
    assert findings[0].observed == 2


def test_fixed_window_alignment_and_edges(make_event: Callable[..., Any]) -> None:
    bucket_start = NOW.replace(minute=0, second=0, microsecond=0)
    events = [
        _event(make_event, 1, bucket_start, source_ip="203.0.113.45"),
        _event(make_event, 2, bucket_start + timedelta(seconds=1), source_ip="203.0.113.45"),
        _event(make_event, 3, bucket_start + timedelta(hours=1), source_ip="203.0.113.45"),
    ]
    rule = _rule(
        window_mode="fixed",
        fixed_alignment="hour",
        tiers=[
            {
                "label": "Hourly pair",
                "count": 2,
                "window_seconds": 3600,
                "severity": "medium",
                "points": 10,
            }
        ],
    )
    findings = evaluate_threshold(rule, events, now=NOW)
    assert len(findings) == 1
    assert findings[0].window_start == bucket_start.isoformat()
    assert findings[0].window_end == (bucket_start + timedelta(hours=1)).isoformat()


# --- correlation window ---------------------------------------------------


def test_correlation_window_inclusive_end(make_event: Callable[..., Any]) -> None:
    first = _event(make_event, 1, NOW, severity="high", source_ip="203.0.113.45")
    edge = _event(
        make_event, 2, NOW + timedelta(minutes=15), severity="high", source_ip="203.0.113.45"
    )
    beyond = _event(
        make_event,
        3,
        NOW + timedelta(minutes=15, seconds=1),
        severity="high",
        source_ip="203.0.113.45",
    )
    for event in (first, edge, beyond):
        event["event_hash"] = compute_event_hash(event)
    links = [
        link
        for component in correlate([first, edge], CorrelationSettings(), NOW)
        for link in component.links
    ]
    assert any(link.kind == "shared_ip" for link in links)
    assert not any(
        link.kind == "shared_ip"
        for component in correlate([first, beyond], CorrelationSettings(), NOW)
        for link in component.links
    )


# --- retention cutoff -----------------------------------------------------


def test_retention_cutoff_is_strict(tmp_initialised_db: Any) -> None:
    db = tmp_initialised_db
    policy = {**DEFAULT_POLICY, "events": {**DEFAULT_POLICY["events"], "low_days": 1}}
    at_cutoff = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
    events = [
        _event(
            lambda **kw: kw,
            1,
            at_cutoff,
            severity="low",
            source="auth_log",
            event_type="failed_login",
            description="d",
        ),
        _event(
            lambda **kw: kw,
            2,
            at_cutoff - timedelta(microseconds=1),
            severity="low",
            source="auth_log",
            event_type="failed_login",
            description="d",
        ),
    ]
    save_events(events, db, allowlisted=False)
    stats = retention_stats(db, policy=policy, now=at_cutoff + timedelta(days=1))
    assert stats["events"]["low"] == 2
    assert stats["events"]["low_old"] == 1
