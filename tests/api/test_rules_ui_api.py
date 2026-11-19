"""Phase 16 API support for the rule builder, severity and allowlist UIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from storage.auth_repository import create_user
from storage.rules_repository import create_rule, update_rule

PASSWORD = "a-long-test-password"


def _login(client: Any, db_path: Path) -> str:
    create_user("admin", PASSWORD, "admin", db_path)
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 200
    return str(client.cookies.get("sentinel_csrf"))


def _definition(identifier: str = "user-example") -> dict[str, Any]:
    return {
        "id": identifier,
        "name": "User example",
        "description": "Failed logins grouped by source IP",
        "kind": "threshold",
        "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
        "scope": {"exclude_allowlisted": True},
        "actions": {"create_incident": True, "notify": True, "tags": []},
        "mitre": [],
        "group_by": ["source_ip"],
        "aggregate": {"type": "count"},
        "window_mode": "sliding",
        "tiers": [
            {
                "label": "Medium",
                "count": 5,
                "window_seconds": 600,
                "severity": "medium",
                "points": 5,
            },
            {
                "label": "High",
                "count": 20,
                "window_seconds": 600,
                "severity": "high",
                "points": 30,
            },
        ],
    }


def test_schema_catalogue_for_builder(api_client: Any, tmp_initialised_db: Path) -> None:
    _login(api_client, tmp_initialised_db)
    body = api_client.get("/api/rules/schema").json()
    assert "fields" in body and "ops" in body
    assert "mitre" in body and "kinds" in body
    assert any(field["name"] == "details.*" for field in body["fields"])
    assert body["limits"]["max_tiers"] == 10


def test_export_returns_all_rules(api_client: Any, tmp_initialised_db: Path) -> None:
    _login(api_client, tmp_initialised_db)
    create_rule(_definition(), "admin", tmp_initialised_db)
    exported = api_client.get("/api/rules/export").json()
    assert any(item["id"] == "user-example" for item in exported)


def test_import_reports_path_errors(api_client: Any, tmp_initialised_db: Path) -> None:
    csrf = _login(api_client, tmp_initialised_db)
    broken = _definition("broken")
    broken["tiers"][0]["count"] = 0
    response = api_client.post(
        "/api/rules/import",
        json={"rules": [_definition("valid-rule"), broken]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == ["valid-rule"]
    assert body["errors"] and "tiers" in body["errors"][0]["path"]


def test_import_reports_duplicate_ids(api_client: Any, tmp_initialised_db: Path) -> None:
    csrf = _login(api_client, tmp_initialised_db)
    create_rule(_definition("existing-rule"), "admin", tmp_initialised_db)
    duplicate = _definition("existing-rule")
    response = api_client.post(
        "/api/rules/import",
        json={"rules": [duplicate]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["created"] == []
    assert response.json()["errors"][0]["path"] == "rules[0].id"


def test_override_test_box_explains_result(api_client: Any, tmp_initialised_db: Path) -> None:
    csrf = _login(api_client, tmp_initialised_db)
    response = api_client.post(
        "/api/severity/overrides/test",
        json={"event": {"event_type": "failed_login", "source_ip": "203.0.113.45"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["severity"] in {"low", "medium", "high", "critical"}
    assert body["severity_source"].startswith(("default", "override:"))


def test_preview_rejects_bad_date_range(api_client: Any, tmp_initialised_db: Path) -> None:
    csrf = _login(api_client, tmp_initialised_db)
    response = api_client.post(
        "/api/rules/preview",
        json={
            "definition": _definition(),
            "since": "2026-11-20T00:00:00+00:00",
            "until": "2026-11-19T00:00:00+00:00",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


def test_restore_version_creates_new_version(api_client: Any, tmp_initialised_db: Path) -> None:
    csrf = _login(api_client, tmp_initialised_db)
    create_rule(_definition(), "admin", tmp_initialised_db)
    changed = _definition()
    changed["name"] = "Changed"
    update_rule("user-example", changed, "admin", tmp_initialised_db)
    response = api_client.post(
        "/api/rules/user-example/versions/1/restore",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["version"] >= 3
    versions = api_client.get("/api/rules/user-example/versions").json()
    assert versions[-1]["version"] >= 3
