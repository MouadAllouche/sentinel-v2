"""Engine lookback audit (Phase 19, extra item 2).

The rules engine must read at least ``window + cooldown`` of history for every
enabled rule, and a 60-second analyze interval must not stop the baseline cycle
from evaluating the last completed hour.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.config import CollectorSettings, load_settings
from core.rules.models import validate_rule
from engine.rules import event_lookback_seconds
from engine.runner import run_once
from storage.database import init_db
from storage.repositories import query_events, save_events
from storage.rules_repository import list_rules

NOW = datetime(2026, 11, 21, 15, 37, tzinfo=UTC)


def _isolated_settings(tmp_path: Path) -> Any:
    """No real machine reads: auth_log is an empty tmp file and snapshots are off."""
    base = load_settings(config_path=None)
    auth_log = tmp_path / "auth.log"
    auth_log.write_text("", encoding="utf-8")
    return replace(
        base,
        paths=replace(base.paths, auth_log=str(auth_log)),
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


def _rule(identifier: str, window: int, cooldown: int) -> Any:
    return validate_rule(
        {
            "id": identifier,
            "name": identifier,
            "description": "lookback audit",
            "kind": "threshold",
            "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
            "scope": {"exclude_allowlisted": True},
            "actions": {"create_incident": True, "notify": True, "tags": []},
            "mitre": [],
            "group_by": ["source_ip"],
            "aggregate": {"type": "count"},
            "window_mode": "sliding",
            "cooldown_seconds": cooldown,
            "tiers": [
                {
                    "label": "Tier",
                    "count": 5,
                    "window_seconds": window,
                    "severity": "medium",
                    "points": 10,
                }
            ],
        }
    )[0]


def test_lookback_covers_every_enabled_rule_window_plus_cooldown() -> None:
    rules = [_rule("short", 60, 0), _rule("long", 3600, 600), _rule("very-long", 7200, 60)]
    lookback = event_lookback_seconds(rules)
    for rule in rules:
        assert lookback >= max(tier.window_seconds for tier in rule.tiers) + rule.cooldown_seconds


def test_lookback_covers_sequence_within_seconds() -> None:
    sequence = validate_rule(
        {
            "id": "sequence-audit",
            "name": "sequence",
            "description": "lookback audit",
            "kind": "sequence",
            "severity": "high",
            "points": 20,
            "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
            "steps": [
                {"match": {"event_types": ["failed_login"]}, "min_count": 1, "window_seconds": 60}
            ],
            "within_seconds": 1800,
            "correlate_on": ["source_ip"],
            "cooldown_seconds": 300,
            "scope": {"exclude_allowlisted": True},
            "actions": {"create_incident": True, "notify": True, "tags": []},
            "mitre": [],
        }
    )[0]
    assert event_lookback_seconds([sequence]) >= 1800 + 300


def test_analyze_cycle_with_60s_interval_keeps_evaluating_last_completed_hour(
    tmp_path: Path,
) -> None:
    """A real engine cycle with the default 60 s interval must still produce the
    baseline anomaly for the last completed hour, without duplicate events."""
    db = tmp_path / "lookback.db"
    init_db(db)
    reference = NOW
    hour_start = reference.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    events = [
        {
            "timestamp": (hour_start + timedelta(minutes=40, seconds=index)).isoformat(),
            "source": "auth_log",
            "event_type": "failed_login",
            "severity": "low",
            "description": "Failed SSH login attempt for admin",
            "username": "admin",
            "source_ip": "203.0.113.45",
        }
        for index in range(12)
    ]
    # Mature baseline needs history older than min_history_hours (24 h).
    history = [
        {
            "timestamp": (NOW - timedelta(days=2, hours=index)).isoformat(),
            "source": "auth_log",
            "event_type": "failed_login",
            "severity": "low",
            "description": "SSH login",
            "username": "alice",
            "source_ip": "198.51.100.7",
        }
        for index in range(3)
    ]
    save_events(events + history, db, allowlisted=False)

    settings = _isolated_settings(tmp_path)
    report = run_once(settings, db, reference, notify=False)
    assert report.ok, report
    first = query_events({"event_type": ["anomaly"]}, db_path=db)["items"]
    assert first, "baseline cycle did not evaluate the last completed hour"

    # A second analyze 60 seconds later (engine interval) must be idempotent.
    run_once(settings, db, reference + timedelta(seconds=60), notify=False)
    second = query_events({"event_type": ["anomaly"]}, db_path=db)["items"]
    assert len(second) == len(first)


def test_enabled_rule_set_lookback_matches_helper(tmp_path: Path) -> None:
    """The helper used by the engine is the one applied to the stored rule set."""
    from engine.rules import event_lookback_seconds as helper

    db = tmp_path / "rules.db"
    init_db(db)
    settings = _isolated_settings(tmp_path)
    run_once(settings, db, NOW, notify=False)
    enabled = [rule for rule in list_rules(db_path=db) if rule.enabled]
    assert helper(enabled) > 0
