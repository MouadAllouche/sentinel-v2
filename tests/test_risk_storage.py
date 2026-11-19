"""Tests for risk persistence, propagation and the scoring cycle (Phase 10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.rules.defaults import DEFAULT_RULES
from engine.scoring import run_scoring
from storage.database import get_connection
from storage.repositories import get_setting, set_setting
from storage.risk_repository import (
    explain_score,
    get_assessment,
    list_severity_changes,
    upsert_risk_assessment,
)
from storage.rules_repository import seed_rules

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


def _finding(rule_id: str, points: int, severity: str = "medium") -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "rule_version": 1,
        "rule_name": rule_id,
        "tier_index": 0,
        "tier_label": "Tier",
        "severity": severity,
        "points": points,
        "window_end": (NOW - timedelta(minutes=5)).isoformat(),
        "evidence_event_ids": [1, 2],
        "explanation": f"{rule_id} matched",
    }


def test_incident_meta_rules_seeded() -> None:
    meta_ids = [
        definition["id"] for definition in DEFAULT_RULES if definition["kind"] == "incident_meta"
    ]
    assert len(meta_ids) == 4
    assert "multiple-related-events" in meta_ids
    assert "drift-after-access" in meta_ids


def test_upsert_explain_and_settings(tmp_initialised_db: Path) -> None:
    assessment = {
        "score": 50,
        "raw_score": 50,
        "capped": False,
        "severity": "high",
        "reasons": [
            {
                "kind": "rule",
                "rule_id": "ssh-bruteforce-by-ip",
                "tier_label": "Sustained attack",
                "points": 50,
                "explanation": "6 failed logins from 203.0.113.45 within 10 min",
            },
            {
                "kind": "summary",
                "points": 0,
                "raw_score": 50,
                "score": 50,
                "severity_basis": "score band",
            },
        ],
    }
    upsert_risk_assessment("incident", 1, assessment, tmp_initialised_db)
    stored = get_assessment("incident", 1, tmp_initialised_db)
    assert stored is not None and stored["score"] == 50
    lines = explain_score("incident", 1, tmp_initialised_db)
    assert any("50" in line and "ssh-bruteforce-by-ip" in line for line in lines)
    upsert_risk_assessment("incident", 1, {**assessment, "score": 60}, tmp_initialised_db)
    assert get_assessment("incident", 1, tmp_initialised_db)["score"] == 60

    set_setting(
        "risk.severity_thresholds",
        {"medium": 20, "high": 40, "critical": 70},
        updated_by="alice",
        db_path=tmp_initialised_db,
    )
    assert get_setting("risk.severity_thresholds", tmp_initialised_db)["high"] == 40


def test_scoring_cycle_propagates_and_is_idempotent(
    tmp_initialised_db: Path, make_event: Any
) -> None:
    seed_rules(tmp_initialised_db)
    connection = get_connection(tmp_initialised_db)
    connection.execute(
        "INSERT INTO incidents(id, correlation_key, title, status, first_seen, last_seen, "
        "severity, risk_score, created_at, updated_at) "
        "VALUES (1, 'score-key', 'Possible brute force', 'open', ?, ?, 'low', 0, ?, ?)",
        (
            (NOW - timedelta(minutes=10)).isoformat(),
            NOW.isoformat(),
            NOW.isoformat(),
            NOW.isoformat(),
        ),
    )
    for event_id in (1, 2):
        connection.execute(
            "INSERT INTO incident_events(incident_id, event_id) VALUES (1, ?)", (event_id,)
        )
    connection.execute(
        "INSERT INTO rule_findings(rule_id, rule_version, group_key, tier_index, severity, "
        "points, window_start, window_end, observed, evidence_event_ids_json, created_at) "
        "VALUES ('ssh-bruteforce-by-ip', 1, 'source_ip=203.0.113.45', 0, 'high', 30, ?, ?, "
        "20, '[1,2]', ?)",
        (
            (NOW - timedelta(minutes=10)).isoformat(),
            (NOW - timedelta(minutes=5)).isoformat(),
            NOW.isoformat(),
        ),
    )
    connection.commit()
    connection.close()

    first = run_scoring(tmp_initialised_db, now=NOW)
    assert first.assessments == 1
    connection = get_connection(tmp_initialised_db)
    row = connection.execute("SELECT risk_score, severity FROM incidents WHERE id = 1").fetchone()
    connection.close()
    assert row["risk_score"] == 30
    assert row["severity"] == "high"
    changes = list_severity_changes(1, tmp_initialised_db)
    assert len(changes) == 1

    second = run_scoring(tmp_initialised_db, now=NOW)
    assert second.assessments == 1
    assert len(list_severity_changes(1, tmp_initialised_db)) == 1


def test_risk_rules_doc_lists_every_seeded_id() -> None:
    docs = Path(__file__).resolve().parents[1] / "docs" / "RISK_RULES.md"
    text = docs.read_text(encoding="utf-8")
    for definition in DEFAULT_RULES:
        assert definition["id"] in text
