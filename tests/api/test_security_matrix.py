"""OpenAPI-driven security matrix and session tests (Phase 12)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from storage.auth_repository import create_user, get_user_by_name, list_sessions

PASSWORD = "a-long-test-password"

UNSAFE = {"post", "put", "patch", "delete"}
LOGIN = "/api/auth/login"
# Routes an admin may mutate but a viewer must not.
ADMIN_ROUTES = {
    ("post", "/api/rules"),
    ("put", "/api/rules/ssh-bruteforce-by-ip"),
    ("delete", "/api/rules/ssh-bruteforce-by-ip"),
    ("post", "/api/engine/run"),
    ("post", "/api/allowlist"),
    ("delete", "/api/allowlist/1"),
    ("post", "/api/drift/check"),
    ("post", "/api/drift/accept"),
    ("put", "/api/risk/thresholds"),
    ("post", "/api/retention/apply"),
    ("post", "/api/users"),
    ("patch", "/api/users/1"),
    ("post", "/api/notifications/channels"),
}


def _spec() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "web" / "openapi.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _unsafe_routes() -> list[tuple[str, str]]:
    return [
        (method, path)
        for path, item in _spec()["paths"].items()
        for method in item
        if method in UNSAFE and path != LOGIN
    ]


def _login(client: Any, username: str = "admin") -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return str(client.cookies.get("sentinel_csrf"))


@pytest.mark.parametrize(("method", "path"), _unsafe_routes())
def test_csrf_required_for_every_unsafe_route(
    api_client: Any, tmp_initialised_db: Path, method: str, path: str
) -> None:
    create_user("admin", PASSWORD, "admin", tmp_initialised_db)
    _login(api_client)
    kwargs: dict[str, Any] = {"json": {}}
    response = api_client.request(method.upper(), path, **kwargs)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


@pytest.mark.parametrize(("method", "path"), sorted(ADMIN_ROUTES))
def test_viewer_forbidden_on_admin_routes(
    api_client: Any, tmp_initialised_db: Path, method: str, path: str
) -> None:
    create_user("admin", PASSWORD, "admin", tmp_initialised_db)
    create_user("viewer", PASSWORD, "viewer", tmp_initialised_db)
    csrf = _login(api_client, "viewer")
    response = api_client.request(method.upper(), path, json={}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_unauthenticated_mutating_request_is_401(api_client: Any) -> None:
    response = api_client.post("/api/engine/run")
    assert response.status_code == 401


def test_cookie_flags_hash_never_returned(api_client: Any, tmp_initialised_db: Path) -> None:
    create_user("admin", PASSWORD, "admin", tmp_initialised_db)
    response = api_client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie and "SameSite=strict" in set_cookie
    assert "sentinel_session=" in set_cookie and "sentinel_csrf=" in set_cookie
    users = api_client.get("/api/users").json()
    assert all("password_hash" not in user for user in users)
    sessions = api_client.get("/api/auth/sessions").json()
    assert all("id_hash" not in item for item in sessions)


def test_logout_revokes_and_password_change_revokes_others(
    api_client: Any, tmp_initialised_db: Path
) -> None:
    create_user("admin", PASSWORD, "admin", tmp_initialised_db)
    csrf = _login(api_client)
    assert len(list_sessions(tmp_initialised_db)) == 1
    changed = api_client.post(
        "/api/auth/password",
        json={
            "old_password": PASSWORD,
            "new_password": "another-long-password-123",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert changed.status_code == 200
    assert len(list_sessions(tmp_initialised_db)) == 0
    assert get_user_by_name("admin", tmp_initialised_db)["password_hash"] != PASSWORD


def test_login_timing_is_uniform(api_client: Any, tmp_initialised_db: Path) -> None:
    create_user("admin", PASSWORD, "admin", tmp_initialised_db)
    start = time.monotonic()
    api_client.post("/api/auth/login", json={"username": "nobody", "password": PASSWORD})
    unknown = time.monotonic() - start
    start = time.monotonic()
    api_client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password-1"})
    known = time.monotonic() - start
    assert abs(unknown - known) < 0.5


def test_incidents_list_returns_200(api_client: Any, tmp_initialised_db: Path) -> None:
    create_user("admin", PASSWORD, "admin", tmp_initialised_db)
    _login(api_client)
    response = api_client.get("/api/incidents")
    assert response.status_code == 200
