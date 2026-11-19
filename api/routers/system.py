"""System, users, audit and saved-filter endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from api.deps import admin_user, current_user, db_path, optional_user
from core.health import get_health
from engine.runner import run_once
from storage.auth_repository import (
    create_saved_filter,
    create_user,
    delete_saved_filter,
    list_saved_filters,
    list_users,
    set_user_disabled,
    update_role,
)
from storage.ops_repository import list_collector_runs, list_cycle_runs
from storage.repositories import list_audit

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=dict[str, Any])
def health(
    request: Request, user: dict[str, Any] | None = Depends(optional_user)
) -> dict[str, Any]:
    full = get_health(db_path(request))
    return full if user else {"status": full["status"]}


@router.get("/collectors", response_model=list[dict[str, Any]])
def collectors(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return list_collector_runs(db_path=db_path(request))


@router.get("/cycles", response_model=list[dict[str, Any]])
def cycles(request: Request, _user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    return list_cycle_runs(db_path=db_path(request))


@router.post("/engine/run", response_model=dict[str, Any])
def engine_run(request: Request, admin: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    report = run_once(request.app.state.settings, db_path(request), datetime.now(UTC))
    from storage.repositories import write_audit

    write_audit(
        admin["username"],
        "engine.run",
        target_type="engine",
        target_id="cycle",
        ip=request.client.host if request.client else None,
        db_path=db_path(request),
    )
    return {"ok": report.ok, "steps": len(report.steps)}


@router.get("/users", response_model=list[dict[str, Any]])
def users(request: Request, _admin: dict[str, Any] = Depends(admin_user)) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in item.items() if key != "password_hash"}
        for item in list_users(db_path(request))
    ]


@router.post("/users", response_model=dict[str, Any], status_code=201)
def add_user(
    payload: dict[str, Any], request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    return {
        "id": create_user(
            payload["username"],
            payload["password"],
            payload.get("role", "viewer"),
            db_path(request),
            actor=admin["username"],
        )
    }


@router.patch("/users/{identifier}", response_model=dict[str, Any])
def patch_user(
    identifier: int,
    payload: dict[str, Any],
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    if "role" in payload:
        update_role(identifier, payload["role"], db_path(request), actor=admin["username"])
    if "disabled" in payload:
        set_user_disabled(
            identifier, bool(payload["disabled"]), db_path(request), actor=admin["username"]
        )
    return {"ok": True}


@router.post("/users/{identifier}/password-reset", response_model=dict[str, Any])
def reset_user_password(
    identifier: int,
    payload: dict[str, Any],
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    from storage.auth_repository import set_password

    set_password(identifier, payload["password"], db_path(request), actor=admin["username"])
    return {"ok": True}


@router.get("/audit", response_model=dict[str, Any])
def audit(
    request: Request, limit: int = 50, _admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    rows = list_audit({}, db_path=db_path(request), limit=limit)
    return {"items": rows, "next_cursor": None}


@router.get("/filters/saved", response_model=list[dict[str, Any]])
def saved_filters(
    request: Request, user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return list_saved_filters(int(user["id"]), db_path(request))


@router.post("/filters/saved", response_model=dict[str, Any], status_code=201)
def add_filter(
    payload: dict[str, Any], request: Request, user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    return {
        "id": create_saved_filter(
            int(user["id"]),
            payload["name"],
            payload["page"],
            payload.get("query", {}),
            db_path(request),
        )
    }


@router.delete("/filters/saved/{identifier}", response_model=dict[str, Any])
def remove_filter(
    identifier: int, request: Request, user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    delete_saved_filter(identifier, int(user["id"]), db_path(request))
    return {"ok": True}


@router.get("/system/info", response_model=dict[str, Any])
def system_info(request: Request, _user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    health = get_health(db_path(request))
    return {"version": "sentinel-2", "db": health["db"]}


@router.get("/anomalies", response_model=list[dict[str, Any]])
def anomalies(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    from storage.repositories import query_events

    items: list[dict[str, Any]] = query_events(
        {"event_type": ["anomaly"]}, db_path=db_path(request)
    )["items"]
    return items
