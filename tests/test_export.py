"""Tests for incident and event exports (Phase 11)."""

from __future__ import annotations

from core.export import export_events_csv, incident_report, render_incident


def test_incident_report_and_markdown() -> None:
    report = incident_report(
        {
            "id": 1,
            "title": "Possible brute force",
            "severity": "high",
            "risk_score": 75,
            "first_seen": "2026-11-15T10:00:00+00:00",
            "last_seen": "2026-11-15T10:10:00+00:00",
            "summary": "Six failed logins then a success",
            "mitre": [{"id": "T1110", "name": "Brute Force"}],
        },
        timeline=[
            {
                "timestamp": "2026-11-15T10:00:00+00:00",
                "kind": "observed",
                "summary": "failed_login",
                "event_type": "failed_login",
            }
        ],
        reasons=[
            {"rule_id": "ssh-bruteforce-by-ip", "points": 45, "tier_label": "Sustained attack"}
        ],
        notes=[{"author": "alice", "body": "Investigating"}],
    )
    assert report["score"] == 75
    markdown = render_incident(report, "md")
    assert "Possible brute force" in markdown
    assert "Observed" in markdown
    assert "T1110" in markdown
    assert "Investigating" in markdown
    pdf = render_incident(report, "pdf")
    assert pdf[:4] == b"%PDF"
    assert b"SENTINEL" in pdf or b"Possible" in pdf


def test_markdown_accepts_string_mitre_ids() -> None:
    report = {
        "generated_at": "2026-11-19T12:00:00+00:00",
        "id": 2,
        "title": "Demo scenario",
        "severity": "high",
        "score": 85,
        "first_seen": "2026-11-19T10:00:00+00:00",
        "last_seen": "2026-11-19T10:10:00+00:00",
        "summary": "Repeated failures",
        "mitre": ["T1110"],
        "timeline": [],
        "reasons": [],
        "notes": [],
        "caveat": "Grouping is inferred, not proof.",
    }
    markdown = render_incident(report, "md")
    assert "T1110" in markdown
    assert render_incident(report, "pdf")[:4] == b"%PDF"


def test_csv_injection_protection_and_cap() -> None:
    rows = [
        {"description": "=cmd|'/c calc'!A0", "source_ip": "203.0.113.45"},
        {"description": "+SUM(A1)", "source_ip": "198.51.100.7"},
        {"description": "-hello", "source_ip": "10.0.0.1"},
        {"description": "@evil", "source_ip": "10.0.0.2"},
    ]
    csv_text = export_events_csv(rows)
    assert "'=cmd" in csv_text
    assert "'+SUM" in csv_text
    assert "'-hello" in csv_text
    assert "'@evil" in csv_text
    many = [{"description": "x"} for _ in range(100_001)]
    assert export_events_csv(many).count("\n") <= 100_001
