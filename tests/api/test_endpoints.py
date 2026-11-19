"""Tests for API routers, validation, OpenAPI and SSE (Phase 12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from storage.auth_repository import create_user
from storage.repositories import save_events

PASSWORD = "a-long-test-password"


def _login(client: Any) -> str:
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 200
    return str(client.cookies.get("sentinel_csrf"))


def _admin(client: Any, db_path: Path) -> str:
    create_user("admin", PASSWORD, "admin", db_path)
    return _login(client)


def test_health_unauth_shape_and_headers(api_client: Any) -> None:
    response = api_client.get("/api/health")
    assert response.status_code == 200
    assert set(response.json()) == {"status"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_events_filters_and_pagination(
    api_client: Any, tmp_initialised_db: Path, make_event: Any
) -> None:
    _admin(api_client, tmp_initialised_db)
    save_events(
        [
            make_event(
                id=i,
                timestamp=f"2026-11-15T10:{i:02d}:00+00:00",
                event_type="failed_login",
                source_ip="203.0.113.45",
                description=f"failure {i}",
            )
            for i in range(5)
        ],
        tmp_initialised_db,
    )
    page = api_client.get("/api/events", params={"event_type": ["failed_login"], "limit": 2})
    assert page.status_code == 200
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"]
    second = api_client.get(
        "/api/events", params={"limit": 2, "cursor": page.json()["next_cursor"]}
    )
    assert not set(item["id"] for item in second.json()["items"]) & set(
        item["id"] for item in page.json()["items"]
    )
    detail = api_client.get("/api/events/1")
    assert detail.status_code == 200
    assert detail.json()["event_type"] == "failed_login"


def test_validation_and_unknown_fields(api_client: Any, tmp_initialised_db: Path) -> None:
    csrf = _admin(api_client, tmp_initialised_db)
    definition = {
        "id": "api-rule",
        "name": "API rule",
        "description": "x",
        "kind": "threshold",
        "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
        "scope": {"exclude_allowlisted": True},
        "actions": {"create_incident": True, "notify": True, "tags": []},
        "mitre": [],
        "group_by": ["source_ip"],
        "aggregate": {"type": "count"},
        "window_mode": "sliding",
        "tiers": [
            {"label": "Low", "count": 3, "window_seconds": 60, "severity": "low", "points": 5}
        ],
    }
    created = api_client.post("/api/rules", json=definition, headers={"X-CSRF-Token": csrf})
    assert created.status_code == 200
    bad = api_client.post(
        "/api/rules", json={**definition, "junk": 1}, headers={"X-CSRF-Token": csrf}
    )
    assert bad.status_code == 422
    preview = api_client.post(
        "/api/rules/preview", json={"definition": definition}, headers={"X-CSRF-Token": csrf}
    )
    assert preview.status_code == 200
    assert "total_findings" in preview.json()


def test_stats_grouped_by_severity(api_client: Any, tmp_initialised_db: Path) -> None:
    _admin(api_client, tmp_initialised_db)
    save_events(
        [
            {
                "timestamp": f"2026-11-19T10:{i:02d}:00+00:00",
                "source": "auth.log",
                "event_type": "failed_login",
                "severity": "low" if i % 2 else "high",
                "description": f"failure {i}",
            }
            for i in range(4)
        ],
        tmp_initialised_db,
    )
    response = api_client.get(
        "/api/events/stats",
        params={
            "bucket": "hour",
            "group_by": "severity",
            "since": "2026-11-19T10:00:00+00:00",
            "until": "2026-11-19T11:00:00+00:00",
        },
    )
    assert response.status_code == 200
    buckets = response.json()["buckets"]
    assert any(item["bucket"].startswith("2026-11-19T10") for item in buckets)
    assert sum(item["total"] for item in buckets) == 4


def test_export_honours_filters(api_client: Any, tmp_initialised_db: Path) -> None:
    _admin(api_client, tmp_initialised_db)
    save_events(
        [
            {
                "timestamp": f"2026-11-19T10:{i:02d}:00+00:00",
                "source": "auth.log",
                "event_type": "failed_login",
                "severity": "low" if i else "critical",
                "description": f"failure {i}",
            }
            for i in range(3)
        ],
        tmp_initialised_db,
    )
    response = api_client.get("/api/events/export", params={"format": "json", "severity": ["low"]})
    assert response.status_code == 200
    rows = json.loads(json.loads(response.text))
    assert len(rows) == 2
    assert all(row["severity"] == "low" for row in rows)


def test_stream_requires_auth(api_client: Any) -> None:
    assert api_client.get("/api/stream").status_code == 401


def test_changes_polling_fallback(api_client: Any, tmp_initialised_db: Path) -> None:
    from storage.notification_repository import record_change

    _admin(api_client, tmp_initialised_db)
    for index in range(3):
        record_change("incident.created", index, tmp_initialised_db)
    first = api_client.get("/api/changes", params={"since": 0, "limit": 2})
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    assert first.json()["items"][0]["type"] == "incident.created"
    assert first.json()["next_cursor"]
    second = api_client.get("/api/changes", params={"since": first.json()["next_cursor"]})
    assert len(second.json()["items"]) == 1


def test_openapi_snapshot_is_current(api_client: Any) -> None:
    response = api_client.get("/api/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    committed = Path(__file__).resolve().parents[2] / "web" / "openapi.json"
    assert committed.exists()
    assert json.loads(committed.read_text(encoding="utf-8")) == spec
