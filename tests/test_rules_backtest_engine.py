"""Tests for backtesting and rule-engine orchestration (Phase 5)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from core.rules.backtest import backtest_rule
from core.rules.engine import evaluate_rules
from core.rules.models import validate_rule
from engine.rules import run_rules
from storage.repositories import count_events, query_events
from storage.rules_repository import create_rule, list_findings

BASE_TIME = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


def _definition(**changes: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": "backtest-rule",
        "name": "Backtest rule",
        "description": "Threshold rule for backtests",
        "kind": "threshold",
        "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
        "scope": {"exclude_allowlisted": True},
        "actions": {"create_incident": True, "notify": True, "tags": []},
        "mitre": ["T1110.001"],
        "group_by": ["source_ip"],
        "aggregate": {"type": "count"},
        "window_mode": "sliding",
        "cooldown_seconds": 0,
        "tiers": [
            {"label": "Low", "count": 3, "window_seconds": 60, "severity": "medium", "points": 10},
        ],
    }
    value.update(changes)
    return value


def _events(make_event: Callable[..., dict[str, Any]], count: int = 4) -> list[dict[str, Any]]:
    return [
        make_event(
            id=i,
            timestamp=(BASE_TIME + timedelta(seconds=i * 10)).isoformat(),
            source_ip="203.0.113.45",
        )
        for i in range(count)
    ]


def test_backtest_counts_noise_and_no_persistence(
    make_event: Callable[..., dict[str, Any]],
) -> None:
    events = _events(make_event)
    result = backtest_rule(
        _definition(),
        events,
        start="2026-11-15T00:00:00+00:00",
        end="2026-11-16T00:00:00+00:00",
    )
    assert result.total_findings == 1
    assert result.by_severity == {"medium": 1}
    assert result.by_tier == {0: 1}
    assert result.distinct_groups == 1
    assert result.noise_per_day == pytest.approx(1.0)
    assert result.findings[0].evidence_event_ids == [0, 1, 2]
    assert "2026-11-15T10:00:00" in result.timeline[0]["bucket"]


def test_backtest_range_and_should_stop(make_event: Callable[..., dict[str, Any]]) -> None:
    events = _events(make_event)
    empty = backtest_rule(
        _definition(),
        events,
        start="2026-11-16T00:00:00+00:00",
        end="2026-11-17T00:00:00+00:00",
    )
    assert empty.total_findings == 0
    stopped = backtest_rule(
        _definition(),
        events,
        start="2026-11-15T00:00:00+00:00",
        end="2026-11-16T00:00:00+00:00",
        should_stop=lambda: True,
    )
    assert stopped.total_findings == 0
    with pytest.raises(ValueError, match="30"):
        backtest_rule(
            _definition(),
            events,
            start="2026-11-01T00:00:00+00:00",
            end="2026-12-05T00:00:00+00:00",
        )


def test_evaluate_rules_is_silent_for_delegated_kinds() -> None:
    rule, _warnings = validate_rule(
        _definition(
            id="reserved-rule",
            name="Reserved rule",
            kind="baseline_metric",
            metric="failed_logins_per_hour",
            subject="global",
            tiers=[
                {
                    "label": "Elevated",
                    "z": 3.0,
                    "min_absolute": 5,
                    "severity": "medium",
                    "points": 10,
                }
            ],
        )
    )
    findings, warnings = evaluate_rules([rule], [], now=BASE_TIME)
    assert findings == []
    assert warnings == []


def test_engine_emits_deterministic_rule_triggered_events(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    create_rule(_definition(), "alice", tmp_initialised_db)
    events = _events(make_event)
    from storage.repositories import save_events

    save_events(events, tmp_initialised_db)
    first = run_rules(tmp_initialised_db, now=BASE_TIME + timedelta(seconds=60))
    assert first.findings_new == 1
    assert first.triggered_events_new == 1
    assert len(list_findings({}, db_path=tmp_initialised_db)) == 1
    triggered = query_events({"event_type": ["rule_triggered"]}, db_path=tmp_initialised_db)
    assert len(triggered["items"]) == 1
    assert triggered["items"][0]["severity_source"] == "rule:backtest-rule"
    second = run_rules(tmp_initialised_db, now=BASE_TIME + timedelta(seconds=60))
    assert second.findings_new == 0
    assert second.triggered_events_new == 0
    assert count_events({}, tmp_initialised_db) == 5


def test_performance_budget(make_event: Callable[..., dict[str, Any]]) -> None:
    import time

    events = [
        make_event(
            id=i,
            timestamp=(BASE_TIME + timedelta(seconds=i % 60)).isoformat(),
            source_ip=f"10.0.{i % 20}.{i % 7}",
        )
        for i in range(200_000)
    ]
    started = time.perf_counter()
    findings, warnings = evaluate_rules([validate_rule(_definition())[0]], events, now=BASE_TIME)
    elapsed = time.perf_counter() - started
    assert elapsed < 30
    assert isinstance(findings, list)
    assert warnings == []
