"""Event endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from api.deps import admin_user, current_user, db_path
from api.schemas import ReapplyRequest
from core.export import export_events_csv
from core.risk_scoring import event_score
from storage.repositories import (
    event_time_series,
    get_event,
    query_events,
    top_values,
)
from storage.severity_repository import reapply_severity

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=dict[str, Any])
def list_events(
    request: Request,
    event_type: list[str] | None = Query(default=None),
    severity: list[str] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    username: str | None = None,
    source_ip: str | None = None,
    process_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
    search: str | None = None,
    allowlisted: bool | None = None,
    incident_id: int | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, le=500, ge=1),
    _user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for key, value in {
        "event_type": event_type,
        "severity": severity,
        "source": source,
        "username": username,
        "source_ip": source_ip,
        "process_name": process_name,
        "since": since,
        "until": until,
        "search": search,
        "allowlisted": allowlisted,
        "incident_id": incident_id,
    }.items():
        if value is not None:
            filters[key] = value
    return query_events(filters, cursor=cursor, limit=limit, db_path=db_path(request))


@router.get("/stats", response_model=dict[str, Any])
def stats(
    request: Request,
    bucket: str = "hour",
    since: str | None = None,
    until: str | None = None,
    _user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    if bucket not in {"hour", "day"}:
        from api.deps import ApiError

        raise ApiError(422, "validation_error", "bucket must be hour or day")
    return event_time_series(
        {"since": since, "until": until}, bucket=bucket, zero_fill=True, db_path=db_path(request)
    )


@router.get("/top", response_model=list[dict[str, Any]])
def top(
    request: Request,
    field: str,
    limit: int = Query(default=10, le=100),
    _user: dict[str, Any] = Depends(current_user),
) -> list[dict[str, Any]]:
    return top_values(field, limit=limit, db_path=db_path(request))


@router.get("/export", response_model=str)
def export_events(
    request: Request,
    format: str = "csv",
    _user: dict[str, Any] = Depends(current_user),
) -> str:
    items = query_events({}, limit=500, db_path=db_path(request))["items"]
    if format == "csv":
        return export_events_csv(items)
    if format == "json":
        import json

        return json.dumps(items, default=str)
    from api.deps import ApiError

    raise ApiError(422, "validation_error", "format must be csv or json")


@router.post("/reapply-severity", response_model=dict[str, Any])
def reapply(
    payload: ReapplyRequest, request: Request, _admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    return reapply_severity(payload.filters, db_path(request), dry_run=payload.dry_run)


@router.get("/{event_id}", response_model=dict[str, Any])
def get_one(
    event_id: int, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    event = get_event(event_id, db_path(request))
    if event is None:
        from api.deps import ApiError

        raise ApiError(404, "not_found", "event not found")
    return {**event, "score": event_score(event)}
