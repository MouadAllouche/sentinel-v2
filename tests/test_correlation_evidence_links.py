"""Evidence/group-key links must follow the relation, not the time window (D-116)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.correlation import CorrelationSettings, correlate
from core.normalizer import compute_event_hash

BASE = datetime(2026, 11, 21, 12, tzinfo=UTC)


def _event(
    make_event: Any, identifier: int, offset: int, event_type: str, **overrides: Any
) -> dict[str, Any]:
    event = make_event(
        id=identifier,
        timestamp=(BASE + timedelta(minutes=offset)).isoformat(),
        event_type=event_type,
        source="rules" if event_type == "rule_triggered" else "auth_log",
        **overrides,
    )
    for key, value in list(event.items()):
        if value is None:
            del event[key]
    event["event_hash"] = compute_event_hash(event)
    return event


def test_evidence_and_group_key_links_ignore_the_15_minute_window(
    make_event: Any,
) -> None:
    trigger_1 = _event(
        make_event,
        100,
        0,
        "rule_triggered",
        severity="high",
        details={
            "rule_id": "r",
            "group_key": "source_ip=203.0.113.45",
            "evidence_event_ids": [1, 2, 3],
            "create_incident": True,
        },
    )
    trigger_2 = _event(
        make_event,
        200,
        300,
        "rule_triggered",  # five hours later
        severity="high",
        details={
            "rule_id": "r",
            "group_key": "source_ip=203.0.113.45",
            "evidence_event_ids": [4],
            "create_incident": True,
        },
    )
    events = [
        _event(make_event, 1, 0, "failed_login", source_ip="203.0.113.45", username="a"),
        _event(make_event, 2, 10, "failed_login", source_ip="203.0.113.45", username="b"),
        _event(make_event, 3, 20, "failed_login", source_ip="203.0.113.45", username="c"),
        trigger_1,
        _event(make_event, 4, 300, "failed_login", source_ip="203.0.113.45", username="d"),
        trigger_2,
        _event(make_event, 5, 600, "failed_login", source_ip="198.51.100.7", username="z"),
    ]
    components = correlate(events, CorrelationSettings(), BASE + timedelta(hours=12))
    links = [link for component in components for link in component.links]
    evidence_pairs = {
        (min(link.a, link.b), max(link.a, link.b)) for link in links if link.kind == "rule_evidence"
    }
    assert evidence_pairs == {(1, 100), (2, 100), (3, 100), (4, 200)}
    assert any(link.kind == "same_group_key" and {link.a, link.b} == {100, 200} for link in links)
    assert not any(5 in (link.a, link.b) for link in links), "unrelated event was linked"
    main = next(component for component in components if 100 in component.event_ids)
    assert set(main.event_ids) == {1, 2, 3, 4, 100, 200}
    assert any(component.event_ids == [5] for component in components)


def _run(sid: str, workdir: Path, rules: Path | None = None) -> Any:
    from scripts.simulator.runner import run_scenario

    return run_scenario(
        sid,
        seed=7,
        workdir=workdir,
        overrides=json.loads(rules.read_text(encoding="utf-8")) if rules else None,
    )


def test_valid_user_spray_with_candidate_rules_makes_one_incident(sim_workdir: Path) -> None:
    result = _run(
        "valid-user-spray-hourly", sim_workdir / "spray", Path("sample_data/slow_attack_rules.json")
    )
    assert len(result.incidents) == 1, [item["id"] for item in result.incidents]
    assert result.incidents[0]["event_ids"]
    from storage.repositories import get_events_by_ids

    stored = get_events_by_ids(result.incidents[0]["event_ids"], result.database)
    failed = [event for event in stored.values() if event["event_type"] == "failed_login"]
    triggered = [event for event in stored.values() if event["event_type"] == "rule_triggered"]
    assert len(failed) == 12
    assert len(triggered) == 2


def test_slow_rotating_unchanged_with_candidate_rules(sim_workdir: Path) -> None:
    result = _run(
        "slow-rotating-bruteforce",
        sim_workdir / "rotating",
        Path("sample_data/slow_attack_rules.json"),
    )
    assert len(result.incidents) == 1
    assert len(result.incidents[0]["event_ids"]) == 38


def test_benign_scenarios_still_have_no_incidents(sim_workdir: Path) -> None:
    for identifier in ("benign-admin-day", "benign-noisy-user", "benign-allowlisted-monitor"):
        result = _run(
            identifier, sim_workdir / "benign", Path("sample_data/slow_attack_rules.json")
        )
        assert result.incidents == [], identifier


def test_extended_incident_summary_matches_real_count_and_last_seen(sim_workdir: Path) -> None:
    import sqlite3

    result = _run(
        "slow-rotating-bruteforce",
        sim_workdir / "summary",
        Path("sample_data/slow_attack_rules.json"),
    )
    assert result.database is not None
    connection = sqlite3.connect(result.database)
    row = connection.execute(
        "SELECT summary, last_seen FROM incidents WHERE id = ?", (result.incidents[0]["id"],)
    ).fetchone()
    timestamps = [
        item[0]
        for item in connection.execute(
            "SELECT e.timestamp FROM incident_events ie JOIN events e ON e.id = ie.event_id "
            "WHERE ie.incident_id = ? ORDER BY e.timestamp",
            (result.incidents[0]["id"],),
        )
    ]
    assert row is not None
    assert f"{len(timestamps)} related events" in row[0]
    assert row[1] == max(timestamps)
