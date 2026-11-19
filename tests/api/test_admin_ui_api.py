"""Phase 17 API support for the behavior/drift/admin pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from storage.auth_repository import create_user
from storage.repositories import write_audit

PASSWORD = "a-long-test-password"


def _login(client: Any, db_path: Path, username: str = "admin") -> str:
    create_user("admin", PASSWORD, "admin", db_path)
    create_user("viewer", PASSWORD, "viewer", db_path)
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return str(client.cookies.get("sentinel_csrf"))


def test_system_info_exposes_admin_facts(
    api_client: Any, tmp_initialised_db: Path, monkeypatch: Any
) -> None:
    _login(api_client, tmp_initialised_db)
    monkeypatch.setenv("SENTINEL_WEBHOOK_SECRET", "value")
    body = api_client.get("/api/system/info").json()
    assert body["notifications_enabled"] is False
    assert body["env_vars"]["SENTINEL_WEBHOOK_SECRET"] is True
    assert body["env_vars"]["SENTINEL_TELEGRAM_TOKEN"] is False
    assert body["schema_version"] >= 1
    assert body["engine"]["interval_seconds"] > 0


def test_channel_secret_must_be_an_env_name(api_client: Any, tmp_initialised_db: Path) -> None:
    csrf = _login(api_client, tmp_initialised_db)
    bad = api_client.post(
        "/api/notifications/channels",
        json={
            "name": "Bad",
            "kind": "webhook",
            "enabled": False,
            "config": {"url": "http://127.0.0.1:9/hook", "secret_env": "lowercase"},
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert bad.status_code == 422
    good = api_client.post(
        "/api/notifications/channels",
        json={
            "name": "Good",
            "kind": "webhook",
            "enabled": False,
            "config": {"url": "http://127.0.0.1:9/hook", "secret_env": "SENTINEL_WEBHOOK_SECRET"},
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert good.status_code == 201


def test_last_admin_cannot_be_disabled(api_client: Any, tmp_initialised_db: Path) -> None:
    csrf = _login(api_client, tmp_initialised_db)
    # Only the admin is active; the seeded viewer is disabled for this test.
    from storage.auth_repository import set_user_disabled

    set_user_disabled(2, True, tmp_initialised_db)
    response = api_client.patch(
        "/api/users/1", json={"disabled": True}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 409


def test_audit_filters(api_client: Any, tmp_initialised_db: Path) -> None:
    _login(api_client, tmp_initialised_db)
    write_audit(
        "admin", "rule.update", target_type="rule", target_id="r1", db_path=tmp_initialised_db
    )
    write_audit(
        "viewer",
        "incident.status",
        target_type="incident",
        target_id="1",
        db_path=tmp_initialised_db,
    )
    body = api_client.get(
        "/api/audit", params={"actor": "admin", "action_prefix": "rule", "limit": 10}
    ).json()
    assert len(body["items"]) == 1
    assert body["items"][0]["actor"] == "admin"
