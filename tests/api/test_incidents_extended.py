"""Phase 15 API support for the incident investigation UI."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from storage.auth_repository import create_user
from storage.database import get_connection
from storage.incident_repository import set_incident_status
from storage.repositories import save_events

PASSWORD = "a-long-test-password"
STAMP = "2026-11-19T10:00:00+00:00"


def _login(client: Any, db_path: Path, username: str = "admin") -> str:
    create_user("admin", PASSWORD, "admin", db_path)
    create_user("viewer", PASSWORD, "viewer", db_path)
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return str(client.cookies.get("sentinel_csrf"))


def _incident(db_path: Path, identifier: int = 1, status: str = "open") -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT OR IGNORE INTO incidents(correlation_key, title, status, first_seen, "
            "last_seen, severity, risk_score, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"demo-{identifier}",
                f"Incident {identifier}",
                status,
                STAMP,
                STAMP,
                "high",
                80,
                STAMP,
                STAMP,
            ),
        )
        connection.execute(
            "INSERT OR IGNORE INTO incident_events(incident_id, event_id, relation_reason, "
            "link_strength) VALUES (?, ?, ?, ?)",
            (identifier, 1, "Same source IP", "strong"),
        )


def _finding(db_path: Path) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT OR IGNORE INTO rule_findings(rule_id, rule_version, group_key, tier_index, "
            "severity, points, window_start, window_end, observed, evidence_event_ids_json, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ssh-bruteforce-by-ip",
                1,
                "203.0.113.45",
                0,
                "high",
                20,
                STAMP,
                STAMP,
                6,
                "[1]",
                STAMP,
            ),
        )


def test_history_endpoint(api_client: Any, tmp_initialised_db: Path) -> None:
    _login(api_client, tmp_initialised_db)
    _incident(tmp_initialised_db)
    set_incident_status(1, "open", "investigating", "admin", "reviewing", tmp_initialised_db)
    response = api_client.get("/api/incidents/1/history")
    assert response.status_code == 200
    body = response.json()
    assert any(entry["to_status"] == "investigating" for entry in body["history"])
    assert isinstance(body["audit"], list)


def test_bulk_status_change(api_client: Any, tmp_initialised_db: Path) -> None:
    csrf = _login(api_client, tmp_initialised_db)
    _incident(tmp_initialised_db, 1)
    _incident(tmp_initialised_db, 2)
    response = api_client.post(
        "/api/incidents/bulk-status",
        json={"ids": [1, 2], "status": "investigating", "reason": "bulk review"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json() == {"updated": 2}
    assert api_client.get("/api/incidents/1").json()["status"] == "investigating"


def test_bulk_status_requires_reason_for_resolved(
    api_client: Any, tmp_initialised_db: Path
) -> None:
    csrf = _login(api_client, tmp_initialised_db)
    _incident(tmp_initialised_db)
    response = api_client.post(
        "/api/incidents/bulk-status",
        json={"ids": [1], "status": "resolved"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


def test_incident_mutations_emit_stream_changes(tmp_initialised_db: Path) -> None:
    _incident(tmp_initialised_db)
    set_incident_status(1, "open", "investigating", "admin", "review", tmp_initialised_db)
    with closing(get_connection(tmp_initialised_db)) as connection:
        kinds = [
            row[0]
            for row in connection.execute(
                "SELECT kind FROM changes WHERE ref_id = ? ORDER BY id", (1,)
            ).fetchall()
        ]
    assert "incident.status_changed" in kinds


def test_status_conflict_on_stale_updated_at(api_client: Any, tmp_initialised_db: Path) -> None:
    csrf = _login(api_client, tmp_initialised_db)
    _incident(tmp_initialised_db)
    response = api_client.post(
        "/api/incidents/1/status",
        json={"status": "investigating", "updated_at": "2020-01-01T00:00:00+00:00"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_explanation_lists_rule_findings(api_client: Any, tmp_initialised_db: Path) -> None:
    _login(api_client, tmp_initialised_db)
    save_events(
        [
            {
                "id": 1,
                "timestamp": STAMP,
                "source": "auth_log",
                "event_type": "failed_login",
                "severity": "high",
                "description": "failed password for root",
                "source_ip": "203.0.113.45",
            }
        ],
        tmp_initialised_db,
    )
    _incident(tmp_initialised_db)
    _finding(tmp_initialised_db)
    body = api_client.get("/api/incidents/1/explanation").json()
    assert any(rule["rule_id"] == "ssh-bruteforce-by-ip" for rule in body["rules"])


def test_pdf_export_is_a_pdf(api_client: Any, tmp_initialised_db: Path) -> None:
    _login(api_client, tmp_initialised_db)
    save_events(
        [
            {
                "id": 1,
                "timestamp": STAMP,
                "source": "auth_log",
                "event_type": "failed_login",
                "severity": "high",
                "description": "failed password for root",
                "source_ip": "203.0.113.45",
            }
        ],
        tmp_initialised_db,
    )
    _incident(tmp_initialised_db)
    response = api_client.get("/api/incidents/1/export", params={"format": "pdf"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")


def test_markdown_export_includes_timeline_reasons_and_notes(
    api_client: Any, tmp_initialised_db: Path
) -> None:
    _login(api_client, tmp_initialised_db)
    save_events(
        [
            {
                "id": 1,
                "timestamp": STAMP,
                "source": "auth_log",
                "event_type": "failed_login",
                "severity": "high",
                "description": "failed password for root",
                "source_ip": "203.0.113.45",
            }
        ],
        tmp_initialised_db,
    )
    _incident(tmp_initialised_db)
    _finding(tmp_initialised_db)
    from storage.incident_repository import add_note

    add_note(1, "admin", "Investigated the failures", tmp_initialised_db)
    response = api_client.get("/api/incidents/1/export", params={"format": "md"})
    assert response.status_code == 200
    body = response.text
    assert "## Timeline" in body and "failed password for root" in body
    assert "## Why this score" in body
    assert "## Notes" in body and "Investigated the failures" in body


def test_incident_list_pagination_and_filters(api_client: Any, tmp_initialised_db: Path) -> None:
    _login(api_client, tmp_initialised_db)
    for index in range(3):
        _incident(tmp_initialised_db, index + 1, status="open" if index < 2 else "resolved")
    first = api_client.get("/api/incidents", params={"limit": 2, "sort": "risk"})
    assert first.status_code == 200
    body = first.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]
    filtered = api_client.get("/api/incidents", params={"status": "resolved"})
    assert len(filtered.json()["items"]) == 1
