"""Tests for baseline storage and the anomaly engine cycle (Phase 8)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.rules.defaults import DEFAULT_RULES
from core.rules.models import validate_rule
from engine.baselines import run_baselines
from storage.baseline_repository import get_baseline_series, list_baselines
from storage.database import get_connection
from storage.repositories import query_events, save_events
from storage.rules_repository import list_findings, list_rules, seed_rules

NOW = datetime(2026, 11, 15, 12, 30, tzinfo=UTC)


def test_baseline_rules_seeded_and_valid() -> None:
    baseline_ids = [
        definition["id"] for definition in DEFAULT_RULES if definition["kind"] == "baseline_metric"
    ]
    assert len(baseline_ids) == 5
    assert "baseline-failed-logins" in baseline_ids
    assert "baseline-sudo-by-user" in baseline_ids
    for definition in DEFAULT_RULES:
        validate_rule(definition)


def test_seeding_includes_baseline_rules(tmp_initialised_db: Path) -> None:
    assert seed_rules(tmp_initialised_db)["rules"] == len(DEFAULT_RULES)
    assert seed_rules(tmp_initialised_db)["rules"] == 0
    assert (
        sum(rule.kind == "baseline_metric" for rule in list_rules(db_path=tmp_initialised_db)) == 5
    )


def test_engine_emits_anomaly_once(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    seed_rules(tmp_initialised_db)
    end = NOW.replace(minute=0, second=0) - timedelta(hours=1)
    events = []
    identifier = 0
    for hours_ago in range(167, -1, -1):
        hour = end - timedelta(hours=hours_ago)
        count = 25 if hour == end else 1
        for _ in range(count):
            events.append(
                make_event(
                    id=identifier,
                    timestamp=hour.isoformat(),
                    event_type="failed_login",
                    source_ip="203.0.113.45",
                    username="admin",
                    description=f"Failed login attempt {identifier}",
                )
            )
            identifier += 1
    save_events(events, tmp_initialised_db)
    first = run_baselines(tmp_initialised_db, now=NOW)
    assert first.anomalies_new >= 1
    anomalies = query_events({"event_type": ["anomaly"]}, db_path=tmp_initialised_db)["items"]
    assert len(anomalies) == 1
    assert anomalies[0]["severity"] == "high"
    assert "unusual, not necessarily malicious" in anomalies[0]["description"]
    assert len(list_baselines(tmp_initialised_db)) >= 1
    findings = list_findings({"rule_id": "baseline-failed-logins"}, db_path=tmp_initialised_db)
    assert len(findings) == 1
    second = run_baselines(tmp_initialised_db, now=NOW)
    assert second.anomalies_new == 0
    assert len(query_events({"event_type": ["anomaly"]}, db_path=tmp_initialised_db)["items"]) == 1


def test_one_baseline_row_per_day(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    seed_rules(tmp_initialised_db)
    end = NOW.replace(minute=0, second=0) - timedelta(hours=1)
    events = [
        make_event(
            id=index,
            timestamp=(end - timedelta(hours=index)).isoformat(),
            event_type="failed_login",
            description=f"failure {index}",
        )
        for index in range(30)
    ]
    save_events(events, tmp_initialised_db)
    run_baselines(tmp_initialised_db, now=NOW)
    run_baselines(tmp_initialised_db, now=NOW + timedelta(hours=1))
    connection = get_connection(tmp_initialised_db)
    count = connection.execute(
        "SELECT COUNT(*) FROM baselines WHERE metric = ? AND subject = ?",
        ("failed_logins_per_hour", "global"),
    ).fetchone()[0]
    connection.close()
    assert count == 1


def test_series_shape(tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]) -> None:
    seed_rules(tmp_initialised_db)
    run_baselines(tmp_initialised_db, now=NOW)
    series = get_baseline_series(
        "failed_logins_per_hour",
        "global",
        since="2026-11-14T00:00:00+00:00",
        db_path=tmp_initialised_db,
    )
    assert series
    assert all({"timestamp", "value", "mean", "upper", "lower"} <= set(item) for item in series)
