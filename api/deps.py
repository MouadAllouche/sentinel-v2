"""FastAPI dependencies: DB path, auth, RBAC and pagination."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Request

from api.security import SESSION_COOKIE, hash_session_token
from core.timeutil import utc_now
from storage.auth_repository import get_session, get_user, touch_session

UNAUTHORIZED = ("unauthorized", "Authentication required")


class ApiError(Exception):
    def __init__(
        self, status: int, code: str, message: str, details: list[dict[str, Any]] | None = None
    ) -> None:
        self.status, self.code, self.message = status, code, message
        self.details = details or []
        super().__init__(message)


def db_path(request: Request) -> str | Path:
    return str(request.app.state.db_path)


def current_user(request: Request) -> dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        raise ApiError(401, *UNAUTHORIZED)
    session = get_session(hash_session_token(token), db_path(request))
    if session is None:
        raise ApiError(401, *UNAUTHORIZED)
    try:
        now = utc_now()
        if datetime.fromisoformat(session["expires_at"]) <= now:
            raise ApiError(401, *UNAUTHORIZED)
        if datetime.fromisoformat(session["last_seen"]) < now - timedelta(
            minutes=request.app.state.settings.api.session_idle_minutes
        ):
            raise ApiError(401, *UNAUTHORIZED)
    except ValueError as exc:
        raise ApiError(401, *UNAUTHORIZED) from exc
    user = get_user(int(session["user_id"]), db_path(request))
    if user is None or user["disabled"]:
        raise ApiError(401, *UNAUTHORIZED)
    touch_session(hash_session_token(token), utc_now().isoformat(), db_path(request))
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


def optional_user(request: Request) -> dict[str, Any] | None:
    try:
        return current_user(request)
    except ApiError:
        return None


def require_role(role: str) -> Callable[[Request], dict[str, Any]]:
    def dependency(request: Request) -> dict[str, Any]:
        user = current_user(request)
        if user["role"] != role:
            raise ApiError(403, "forbidden", f"Requires {role} role")
        return user

    return dependency


admin_user = require_role("admin")


def pagination(limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
    if not 1 <= limit <= 500:
        raise ApiError(422, "validation_error", "limit must be 1..500")
    return {"limit": limit, "cursor": cursor}
