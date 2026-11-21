"""The standard scenario end to end, isolated in tmp_path (Phase 18)."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.config import CollectorSettings, load_settings
from engine.ingest import prepare_event
from engine.runner import run_once
from storage.incident_repository import list_incidents
from storage.repositories import count_events, query_events
from storage.risk_repository import get_assessment

BASE = datetime(2026, 11, 20, 12, tzinfo=UTC)


def _raw(identifier: int, seconds: int, event_type: str, **extra: Any) -> dict[str, Any]:
    return {
        "timestamp": (BASE + timedelta(seconds=seconds)).isoformat(),
        "source": "auth_log",
        "event_type": event_type,
        "severity": "low",
        "description": f"{event_type} for admin from 203.0.113.45",
        "username": "admin",
        "source_ip": "203.0.113.45",
        **extra,
    }


def test_full_scenario_outcomes_and_idempotence(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    # This is a pipeline test, not a live-collection test: disable machine
    # collectors and point auth_log at an empty tmp file, so nothing reads
    # /var/log or the live network/process state.
    base_settings = load_settings(config_path=None)
    auth_log = tmp_initialised_db.parent / "auth.log"
    auth_log.write_text("", encoding="utf-8")
    settings = replace(
        base_settings,
        paths=replace(base_settings.paths, auth_log=str(auth_log)),
        collectors=CollectorSettings(
            auth_source="auth_log",
            journald_unit="ssh",
            network=False,
            listening=False,
            processes=False,
            filesystem=False,
            dpkg=False,
            system=False,
            max_process_events_per_run=0,
        ),
    )
    raw = [_raw(index + 1, index * 2, "failed_login") for index in range(25)]
    raw.extend(_raw(200 + index, 400 + index, "failed_login") for index in range(55))
    raw.append(_raw(100, 60, "successful_login"))
    raw.append(_raw(101, 70, "sudo_command", process_name="sudo"))
    prepared = [prepare_event(item, tmp_initialised_db, now=BASE) for item in raw]
    from storage.repositories import save_events

    save_events([item[0] for item in prepared if item], tmp_initialised_db)

    from storage.rules_repository import seed_rules
    from storage.severity_repository import seed_defaults

    seed_defaults(tmp_initialised_db)
    seed_rules(tmp_initialised_db)
    first = run_once(settings, tmp_initialised_db, BASE, notify=False)
    assert first.ok

    from core.correlation import Component
    from core.normalizer import compute_event_hash
    from core.timeline import build_timeline, explain_incident
    from storage.repositories import get_events_by_ids
    from storage.rules_repository import list_findings

    incidents = list_incidents(db_path=tmp_initialised_db)
    assert len(incidents) == 1  # one main incident for the scenario
    findings = list_findings({}, db_path=tmp_initialised_db, limit=500)
    tiers = [item["severity"] for item in findings]
    assert "high" in tiers and "critical" in tiers  # the 5/20/50 tiers firing
    triggered = query_events({"event_type": ["rule_triggered"]}, db_path=tmp_initialised_db)[
        "items"
    ]
    assert len(triggered) >= len(findings)

    stored = incidents[0]
    assert stored["status"] in {"open", "investigating"}
    events = list(get_events_by_ids(stored.get("event_ids", []), tmp_initialised_db).values())
    for event in events:
        event.setdefault("event_hash", compute_event_hash(event))
    component = Component(events=events)
    timeline = build_timeline(component, events, component.links, findings)
    assert [entry["event_type"] for entry in timeline][:2] == ["failed_login", "failed_login"]
    assert any(entry["kind"] == "inferred" for entry in timeline)
    explanation = explain_incident(component, events, findings)
    assert any("not proof of a single actor" in item for item in explanation["caveats"])

    assessment = get_assessment("incident", stored["id"], tmp_initialised_db)
    assert assessment is not None
    reasons = [item for item in assessment["reasons"] if item.get("points", 0) > 0]
    raw = sum(int(item["points"]) for item in reasons)
    assert raw == sum(int(item.get("points", 0)) for item in assessment["reasons"])
    assert assessment["score"] == min(100, raw)
    assert assessment["severity"] == "critical"
    assert raw <= 100  # score stays within the documented 0-100 band

    before = count_events(db_path=tmp_initialised_db)
    second = run_once(settings, tmp_initialised_db, BASE, notify=False)
    assert second.ok
    assert count_events(db_path=tmp_initialised_db) == before


def test_shuffled_event_order_is_equivalent(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    events = [
        make_event(
            id=index + 1,
            timestamp=(BASE + timedelta(seconds=index * 3)).isoformat(),
            event_type="failed_login",
            source_ip="203.0.113.45",
        )
        for index in range(10)
    ]
    shuffled = list(events)
    random.Random(7).shuffle(shuffled)  # noqa: S311 - deterministic test shuffle, not security
    from storage.repositories import save_events

    save_events(events, tmp_initialised_db)
    first = query_events({}, db_path=tmp_initialised_db)
    shuffled_db = tmp_initialised_db.parent / "shuffled.db"
    from storage.database import init_db

    init_db(shuffled_db)
    save_events(shuffled, shuffled_db)
    second = query_events({}, db_path=shuffled_db)

    def identity(page: dict[str, Any]) -> set[tuple[Any, ...]]:
        return {
            (item["timestamp"], item["description"], item["severity"]) for item in page["items"]
        }

    assert identity(first) == identity(second)
