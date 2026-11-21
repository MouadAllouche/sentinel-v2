"""Tests for API authentication, CSRF and RBAC (Phase 12)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from storage.auth_repository import create_user, list_sessions

PASSWORD = "a-long-test-password"


def _login(client: Any, username: str = "admin", password: str = PASSWORD, **kwargs: Any) -> Any:
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}, **kwargs
    )


def _create_users(db_path: Any) -> None:
    create_user("admin", PASSWORD, "admin", db_path)
    create_user("viewer", PASSWORD, "viewer", db_path)


def test_login_sets_cookies_and_me(api_client: Any, tmp_initialised_db: Path) -> None:
    _create_users(tmp_initialised_db)
    response = _login(api_client)
    assert response.status_code == 200
    assert response.json() == {"username": "admin", "role": "admin"}
    session = api_client.cookies.get("sentinel_session")
    csrf = api_client.cookies.get("sentinel_csrf")
    assert session and csrf and session != csrf
    assert api_client.get("/api/auth/me").json()["username"] == "admin"
    assert len(list_sessions(tmp_initialised_db)) == 1


def test_login_failure_is_uniform_and_locks(api_client: Any, tmp_initialised_db: Path) -> None:
    _create_users(tmp_initialised_db)
    first = _login(api_client, password="wrong-password-123")
    missing = _login(api_client, username="nobody")
    assert first.status_code == missing.status_code == 401
    assert first.json() == missing.json()
    for _ in range(5):
        _login(api_client, password="wrong-password-123")
    locked = _login(api_client)
    assert locked.status_code == 401
    assert locked.json() == first.json()  # uniform, never reveals lockout state


def test_csrf_required_on_unsafe_methods(api_client: Any, tmp_initialised_db: Path) -> None:
    _create_users(tmp_initialised_db)
    _login(api_client)
    response = api_client.post("/api/engine/run")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
    csrf = api_client.cookies.get("sentinel_csrf")
    allowed = api_client.post("/api/engine/run", headers={"X-CSRF-Token": csrf})
    assert allowed.status_code == 200


def test_origin_mismatch_rejected(api_client: Any, tmp_initialised_db: Path) -> None:
    _create_users(tmp_initialised_db)
    _login(api_client)
    csrf = api_client.cookies.get("sentinel_csrf")
    denied = api_client.post(
        "/api/engine/run",
        headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
    )
    assert denied.status_code == 403


def test_reverse_proxy_public_origin_accepted(api_client: Any, tmp_initialised_db: Path) -> None:
    """The Next.js rewrite changes Host to the internal bind address; the
    browser-facing origin is carried in X-Forwarded-* and must be honoured."""
    _create_users(tmp_initialised_db)
    _login(api_client)
    csrf = api_client.cookies.get("sentinel_csrf")
    allowed = api_client.post(
        "/api/engine/run",
        headers={
            "X-CSRF-Token": str(csrf),
            "Origin": "http://127.0.0.1:3000",
            "X-Forwarded-Host": "127.0.0.1:3000",
            "X-Forwarded-Proto": "http",
            "X-Forwarded-Port": "3000",
        },
    )
    assert allowed.status_code == 200

    spoofed = api_client.post(
        "/api/engine/run",
        headers={
            "X-CSRF-Token": str(csrf),
            "Origin": "https://evil.example",
            "X-Forwarded-Host": "127.0.0.1:3000",
            "X-Forwarded-Proto": "http",
        },
    )
    assert spoofed.status_code == 403


def test_rbac_viewer_cannot_mutate(api_client: Any, tmp_initialised_db: Path) -> None:
    _create_users(tmp_initialised_db)
    _login(api_client, username="viewer")
    csrf = api_client.cookies.get("sentinel_csrf")
    response = api_client.post("/api/engine/run", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
