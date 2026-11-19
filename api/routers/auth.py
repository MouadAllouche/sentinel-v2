"""Authentication endpoints."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from api.deps import ApiError, admin_user, current_user, db_path
from api.schemas import LoginRequest, PasswordChange
from api.security import CSRF_COOKIE, SESSION_COOKIE, csrf_token, hash_session_token
from core.auth import (
    dummy_hash,
    needs_rehash,
    new_session_token,
    validate_password,
    verify_password,
)
from core.timeutil import utc_now
from storage.auth_repository import (
    add_failed_login,
    create_session,
    delete_session,
    get_user_by_name,
    list_sessions,
    reset_login_failures,
    revoke_user_sessions,
    set_password,
)
from storage.repositories import write_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

UNIFORM = ("unauthorized", "Invalid credentials")


def _set_cookies(response: Response, session_id: str, secure: bool = False) -> None:
    response.set_cookie(
        SESSION_COOKIE, session_id, httponly=True, samesite="strict", path="/", secure=secure
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token(session_id),
        httponly=False,
        samesite="strict",
        path="/",
        secure=secure,
    )


@router.post("/login", response_model=dict[str, Any])
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    from datetime import datetime

    path = db_path(request)
    user = get_user_by_name(payload.username, path)
    # Always perform one scrypt verification so response timing is uniform.
    verified = verify_password(payload.password, user["password_hash"] if user else dummy_hash())
    locked = bool(
        user and user["locked_until"] and datetime.fromisoformat(user["locked_until"]) > utc_now()
    )
    if user is None or not verified or user["disabled"] or locked:
        if user is not None and not user["disabled"] and not locked and not verified:
            add_failed_login(
                payload.username,
                request.client.host if request.client else "",
                path,
                actor=user["username"],
            )
        raise ApiError(401, *UNIFORM)
    reset_login_failures(payload.username, path)
    if needs_rehash(user["password_hash"]):
        from core.auth import hash_password
        from storage.auth_repository import update_password_hash

        update_password_hash(int(user["id"]), hash_password(payload.password), path)
    revoke_user_sessions(int(user["id"]), path)
    token = new_session_token()
    identifier = hash_session_token(token)
    settings = request.app.state.settings
    expires = utc_now() + timedelta(hours=settings.api.session_absolute_hours)
    create_session(
        identifier,
        int(user["id"]),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        expires_at=expires.isoformat(),
        db_path=path,
    )
    write_audit(
        user["username"],
        "auth.login",
        target_type="user",
        target_id=str(user["id"]),
        ip=request.client.host if request.client else None,
        db_path=path,
    )
    _set_cookies(response, token, secure=bool(getattr(settings.api, "secure_cookies", False)))
    return {"username": user["username"], "role": user["role"]}


@router.post("/logout", response_model=dict[str, Any])
def logout(
    request: Request, response: Response, user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE, "")
    delete_session(hash_session_token(token), db_path(request))
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=dict[str, Any])
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user


@router.post("/password", response_model=dict[str, Any])
def change_password(
    payload: PasswordChange, request: Request, user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    from storage.auth_repository import get_user

    path = db_path(request)
    stored = get_user(int(user["id"]), path)
    if stored is None or not verify_password(payload.old_password, stored["password_hash"]):
        raise ApiError(401, *UNIFORM)
    validate_password(payload.new_password)
    set_password(int(user["id"]), payload.new_password, path, actor=user["username"])
    return {"ok": True}


@router.get("/sessions", response_model=list[dict[str, Any]])
def sessions(
    request: Request, _admin: dict[str, Any] = Depends(admin_user)
) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in item.items() if key != "id_hash"}
        for item in list_sessions(db_path(request))
    ]


@router.delete("/sessions/{identifier}", response_model=dict[str, Any])
def revoke_session(
    identifier: str, request: Request, _admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    delete_session(identifier, db_path(request))
    write_audit(
        _admin["username"],
        "auth.session_revoke",
        target_type="session",
        target_id=identifier,
        db_path=db_path(request),
    )
    return {"ok": True}
