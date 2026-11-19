"""Tests for incident planning, timeline, workflow and MITRE (Phase 7)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from core.correlation import CorrelationSettings, correlate
from core.incidents import (
    IncidentChange,
    apply_status_transition,
    plan_incidents,
    summarize_incident,
    title_for,
)
from core.mitre import mitre_for_rules, mitre_table
from core.normalizer import compute_event_hash
from core.timeline import build_timeline, explain_incident
from storage.database import get_connection
from storage.incident_repository import (
    add_incident_event,
    add_note,
    apply_incidents,
    get_incident,
    list_incidents,
    list_notes,
    list_status_history,
    set_incident_status,
)
from storage.repositories import save_events

BASE = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


def _event(
    make_event: Callable[..., dict[str, Any]],
    identifier: int,
    seconds: int,
    **overrides: Any,
) -> dict[str, Any]:
    event = make_event(
        id=identifier,
        timestamp=(BASE + timedelta(seconds=seconds)).isoformat(),
        event_type=overrides.pop("event_type", "failed_login"),
        severity=overrides.pop("severity", "medium"),
    )
    event.update(overrides)
    for key, value in list(event.items()):
        if value is None:
            del event[key]
    event["event_hash"] = compute_event_hash(event)
    return event


def _plan(events: list[dict[str, Any]], **kwargs: Any) -> list[IncidentChange]:
    components = correlate(events, CorrelationSettings(), now=BASE + timedelta(hours=1))
    return plan_incidents(components, [], now=BASE + timedelta(hours=1), **kwargs)


def test_plan_create_and_idempotent(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [
        _event(make_event, 1, 0, source_ip="203.0.113.45", username="admin"),
        _event(make_event, 2, 60, source_ip="203.0.113.45", username="admin"),
    ]
    changes = _plan(events)
    assert len(changes) == 1
    assert changes[0].action == "create"
    assert changes[0].incident["correlation_key"]

    existing = [
        {
            "id": 1,
            "correlation_key": changes[0].incident["correlation_key"],
            "event_ids": [1, 2],
            "status": "open",
            "last_seen": events[-1]["timestamp"],
        }
    ]
    again = plan_incidents(
        correlate(events, CorrelationSettings(), now=BASE + timedelta(hours=1)),
        existing,
        now=BASE + timedelta(hours=1),
    )
    assert all(change.action == "nochange" for change in again)


def test_plan_merge_and_reopen(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [
        _event(make_event, 1, 0, source_ip="203.0.113.45"),
        _event(make_event, 2, 60, source_ip="203.0.113.45"),
        _event(make_event, 3, 120, source_ip="203.0.113.45"),
    ]
    components = correlate(events, CorrelationSettings(), now=BASE + timedelta(hours=1))
    existing = [
        {"id": 1, "event_ids": [1], "status": "open", "last_seen": events[0]["timestamp"]},
        {"id": 2, "event_ids": [3], "status": "open", "last_seen": events[2]["timestamp"]},
    ]
    changes = plan_incidents(components, existing, now=BASE + timedelta(hours=1))
    assert any(change.action == "merge" for change in changes)

    closed = [
        {
            "id": 1,
            "event_ids": [1],
            "status": "resolved",
            "last_seen": (BASE - timedelta(hours=10)).isoformat(),
        }
    ]
    reopened = plan_incidents(components, closed, now=BASE + timedelta(hours=1))
    assert any(change.action == "create" for change in reopened)


def test_title_summary_timeline_and_caveats(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [
        _event(make_event, 1, 0, source_ip="203.0.113.45", username="admin"),
        _event(make_event, 2, 60, source_ip="203.0.113.45", username="admin"),
    ]
    component = correlate(events, CorrelationSettings(), now=BASE + timedelta(hours=1))[0]
    title = title_for(component, [])
    assert "203.0.113.45" in title
    summary = summarize_incident(component, [])
    assert "2" in summary
    timeline = build_timeline(component, events, component.links, [])
    assert [entry["event_id"] for entry in timeline] == [1, 2]
    assert all(entry["kind"] == "observed" for entry in timeline)
    explanation = explain_incident(component, events, [])
    assert any("not proof of a single actor" in caveat for caveat in explanation["caveats"])


def test_status_transition_matrix() -> None:
    assert apply_status_transition("open", "investigating", None) == "investigating"
    assert apply_status_transition("investigating", "resolved", "checked logs") == "resolved"
    assert apply_status_transition("investigating", "false_positive", "benign") == "false_positive"
    with pytest.raises(ValueError):
        apply_status_transition("open", "resolved", None)
    with pytest.raises(ValueError):
        apply_status_transition("open", "closed", None)
    with pytest.raises(ValueError):
        apply_status_transition("resolved", "open", None)
    assert apply_status_transition("resolved", "investigating", None) == "investigating"


def test_mitre_union_and_order() -> None:
    table = mitre_table()
    assert "T1110.001" in table
    assert "T1059" in table
    result = mitre_for_rules(["T1059", "T1110.001", "T1110.001"])
    ids = [item["id"] for item in result]
    assert ids == ["T1110.001", "T1059"]
    assert all("indicative" in item["label"].lower() for item in result)


def test_incident_storage_and_workflow(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    events = [
        _event(make_event, 1, 0, source_ip="203.0.113.45"),
        _event(make_event, 2, 60, source_ip="203.0.113.45"),
    ]
    save_events(events, tmp_initialised_db)
    changes = _plan(events)
    identifiers = apply_incidents(changes, tmp_initialised_db, events=events)
    assert len(identifiers) == 1
    incident_id = identifiers[0]
    stored = get_incident(incident_id, tmp_initialised_db)
    assert stored is not None
    assert stored["status"] == "open"
    assert len(list_incidents({}, tmp_initialised_db)) == 1
    add_incident_event(incident_id, 1, "Same source IP", "strong", tmp_initialised_db)
    connection = get_connection(tmp_initialised_db)
    count = connection.execute(
        "SELECT COUNT(*) FROM incident_events WHERE incident_id = ?", (incident_id,)
    ).fetchone()[0]
    connection.close()
    assert count == 2
    add_note(incident_id, "alice", "Investigating", tmp_initialised_db)
    assert len(list_notes(incident_id, tmp_initialised_db)) == 1
    set_incident_status(incident_id, "open", "investigating", "alice", None, tmp_initialised_db)
    assert get_incident(incident_id, tmp_initialised_db)["status"] == "investigating"
    assert len(list_status_history(incident_id, tmp_initialised_db)) == 1


def test_apply_incidents_persists_link_reasons(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    events = [
        _event(make_event, 1, 0, source_ip="203.0.113.45"),
        _event(make_event, 2, 60, source_ip="203.0.113.45"),
    ]
    component = correlate(events, CorrelationSettings(), now=BASE + timedelta(hours=1))[0]
    changes = plan_incidents([component], [], now=BASE + timedelta(hours=1))
    apply_incidents(changes, tmp_initialised_db, events=events, links=component.links)
    connection = get_connection(tmp_initialised_db)
    rows = connection.execute(
        "SELECT relation_reason, link_strength FROM incident_events"
    ).fetchall()
    connection.close()
    assert rows and all(row["relation_reason"] for row in rows)
    assert {row["link_strength"] for row in rows} == {"strong"}


def test_merge_keeps_older_incident_id(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    connection = get_connection(tmp_initialised_db)
    for identifier, key in ((1, "key-1"), (2, "key-2")):
        connection.execute(
            "INSERT INTO incidents(id, correlation_key, title, status, first_seen, last_seen, "
            "severity, created_at, updated_at) VALUES (?, ?, ?, 'open', ?, ?, 'medium', ?, ?)",
            (
                identifier,
                key,
                "old",
                "2026-11-15T10:00:00+00:00",
                "2026-11-15T10:00:00+00:00",
                "2026-11-15T10:00:00+00:00",
                "2026-11-15T10:00:00+00:00",
            ),
        )
    connection.execute("INSERT INTO incident_events(incident_id, event_id) VALUES (2, 3)")
    connection.commit()
    connection.close()
    events = [
        _event(make_event, 1, 0, source_ip="203.0.113.45"),
        _event(make_event, 2, 60, source_ip="203.0.113.45"),
        _event(make_event, 3, 120, source_ip="203.0.113.45"),
    ]
    components = correlate(events, CorrelationSettings(), now=BASE + timedelta(hours=1))
    changes = plan_incidents(
        components,
        [
            {"id": 1, "event_ids": [1], "status": "open", "last_seen": events[0]["timestamp"]},
            {"id": 2, "event_ids": [3], "status": "open", "last_seen": events[2]["timestamp"]},
        ],
        now=BASE + timedelta(hours=1),
    )
    assert any(change.action == "merge" and change.into == 1 for change in changes)
    apply_incidents(
        [change for change in changes if change.action == "merge"],
        tmp_initialised_db,
        events=events,
        links=[],
    )
    assert get_incident(1, tmp_initialised_db)["status"] == "open"
    assert get_incident(2, tmp_initialised_db)["status"] == "merged"
    assert 3 in get_incident(1, tmp_initialised_db)["event_ids"]


def test_reopen_creates_new_incident(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    events = [
        _event(make_event, 1, 0, source_ip="203.0.113.45"),
        _event(make_event, 2, 60, source_ip="203.0.113.45"),
    ]
    component = correlate(events, CorrelationSettings(), now=BASE + timedelta(hours=1))[0]
    connection = get_connection(tmp_initialised_db)
    connection.execute(
        "INSERT INTO incidents(id, correlation_key, title, status, first_seen, last_seen, "
        "severity, created_at, updated_at) VALUES (1, ?, 'old', 'resolved', ?, ?, "
        "'medium', ?, ?)",
        (
            component.correlation_key,
            component.events[0]["timestamp"],
            component.events[-1]["timestamp"],
            "2026-11-15T10:00:00+00:00",
            "2026-11-15T10:00:00+00:00",
        ),
    )
    connection.commit()
    connection.close()
    changes = plan_incidents(
        [component],
        [
            {
                "id": 1,
                "event_ids": [1],
                "status": "resolved",
                "last_seen": (BASE - timedelta(hours=10)).isoformat(),
            }
        ],
        now=BASE + timedelta(hours=1),
    )
    apply_incidents(changes, tmp_initialised_db, events=events, links=component.links)
    assert len(list_incidents({}, tmp_initialised_db)) == 2
    assert any(item["status"] == "open" for item in list_incidents({}, tmp_initialised_db))


def test_findings_reach_title_summary_and_mitre(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [
        _event(make_event, 1, 0, source_ip="203.0.113.45"),
        _event(make_event, 2, 60, source_ip="203.0.113.45"),
    ]
    component = correlate(events, CorrelationSettings(), now=BASE + timedelta(hours=1))[0]
    findings = [
        {"rule_id": "ssh-bruteforce-by-ip", "tier_label": "Repeated failures", "severity": "medium"}
    ]
    change = plan_incidents([component], [], now=BASE + timedelta(hours=1), findings=findings)[0]
    assert "ssh-bruteforce-by-ip" in change.incident["summary"]
    assert change.incident["mitre"]
    assert any(item["id"] == "T1110.001" for item in change.incident["mitre"])


def test_creation_gate_requires_medium_anchor(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [
        _event(make_event, 1, 0, source_ip="203.0.113.45", severity="low"),
        _event(make_event, 2, 60, source_ip="203.0.113.45", severity="low"),
    ]
    assert _plan(events) == []


def test_incident_worked_example(make_event: Callable[..., dict[str, Any]]) -> None:
    failures = [
        _event(
            make_event,
            i,
            i * 40,
            source_ip="203.0.113.45",
            username="admin",
            event_type="failed_login",
        )
        for i in range(6)
    ]
    success = _event(
        make_event,
        100,
        420,
        source_ip="203.0.113.45",
        username="admin",
        event_type="successful_login",
    )
    sudo = _event(
        make_event,
        101,
        540,
        source_ip="203.0.113.45",
        username="admin",
        event_type="sudo_command",
        severity="low",
        process_name="visudo",
    )
    drift = _event(
        make_event,
        102,
        720,
        source_ip=None,
        username="admin",
        event_type="config_drift",
        severity="high",
        file_path="/etc/sudoers",
    )
    unrelated = _event(
        make_event,
        200,
        300,
        source_ip="198.51.100.7",
        username="root",
        event_type="failed_login",
        severity="low",
    )
    events = failures + [success, sudo, drift, unrelated]

    components = correlate(events, CorrelationSettings(), now=BASE + timedelta(hours=1))
    assert len(components) == 2
    main = max(components, key=lambda component: len(component.events))
    assert 102 in [event["id"] for event in main.events]
    assert any(link.kind == "time_proximity_host" for link in main.links)
    changes = plan_incidents(components, [], now=BASE + timedelta(hours=1))
    creates = [change for change in changes if change.action == "create"]
    assert len(creates) == 1
    assert creates[0].incident["title"] or title_for(main, [])
