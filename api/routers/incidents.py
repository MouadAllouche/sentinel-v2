"""Incident endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from api.deps import ApiError, admin_user, current_user, db_path
from api.schemas import AssigneeUpdate, NoteCreate, StatusChange
from core.correlation import Component
from core.export import incident_report, render_incident
from core.incidents import apply_status_transition
from core.normalizer import compute_event_hash
from core.timeline import build_timeline, explain_incident
from storage.incident_repository import (
    add_note,
    get_incident,
    list_incidents,
    list_notes,
    set_assignee,
    set_incident_status,
)
from storage.repositories import get_events_by_ids
from storage.risk_repository import get_assessment

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


def _component(
    incident: dict[str, Any], request: Request
) -> tuple[Component, list[dict[str, Any]]]:
    events = list(get_events_by_ids(incident.get("event_ids", []), db_path(request)).values())
    for event in events:
        event.setdefault("event_hash", compute_event_hash(event))
    return Component(events=events), events


@router.get("", response_model=list[dict[str, Any]])
def incidents(
    request: Request,
    status: str | None = None,
    severity: str | None = None,
    _user: dict[str, Any] = Depends(current_user),
) -> list[dict[str, Any]]:
    filters = {
        key: value
        for key, value in {"status": status, "severity": severity}.items()
        if value is not None
    }
    return list_incidents(filters, db_path=db_path(request))


@router.get("/{identifier}", response_model=dict[str, Any])
def show(
    identifier: int, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    incident = get_incident(identifier, db_path(request))
    if incident is None:
        raise ApiError(404, "not_found", "incident not found")
    return {**incident, "assessment": get_assessment("incident", identifier, db_path(request))}


@router.get("/{identifier}/timeline", response_model=list[dict[str, Any]])
def timeline(
    identifier: int, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    incident = get_incident(identifier, db_path(request))
    if incident is None:
        raise ApiError(404, "not_found", "incident not found")
    component, events = _component(incident, request)
    import json

    from storage.rules_repository import list_findings

    incident_events = set(incident.get("event_ids", []))
    findings = []
    for item in list_findings({}, db_path=db_path(request)):
        evidence = set(json.loads(item.get("evidence_event_ids_json") or "[]"))
        if evidence & incident_events:
            findings.append(item)
    return build_timeline(component, events, component.links, findings)


@router.get("/{identifier}/explanation", response_model=dict[str, Any])
def explanation(
    identifier: int, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    incident = get_incident(identifier, db_path(request))
    if incident is None:
        raise ApiError(404, "not_found", "incident not found")
    component, events = _component(incident, request)
    return explain_incident(component, events, [])


@router.get("/{identifier}/graph", response_model=dict[str, Any])
def graph(
    identifier: int, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    incident = get_incident(identifier, db_path(request))
    if incident is None:
        raise ApiError(404, "not_found", "incident not found")
    component, events = _component(incident, request)
    nodes = set()
    for event in events:
        for key in ("source_ip", "username", "process_name", "file_path"):
            if event.get(key):
                nodes.add((key, str(event[key])))
    return {
        "nodes": [{"kind": kind, "value": value} for kind, value in sorted(nodes)],
        "edges": [
            {"a": link.a, "b": link.b, "strength": link.strength, "reason": link.reason}
            for link in component.links
        ],
    }


@router.post("/{identifier}/status", response_model=dict[str, Any])
def status(
    identifier: int,
    payload: StatusChange,
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    incident = get_incident(identifier, db_path(request))
    if incident is None:
        raise ApiError(404, "not_found", "incident not found")
    apply_status_transition(str(incident["status"]), payload.status, payload.reason)
    set_incident_status(
        identifier,
        str(incident["status"]),
        payload.status,
        admin["username"],
        payload.reason,
        db_path(request),
    )
    return {"status": payload.status}


@router.get("/{identifier}/notes", response_model=list[dict[str, Any]])
def notes(
    identifier: int, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return list_notes(identifier, db_path(request))


@router.post("/{identifier}/notes", response_model=dict[str, Any], status_code=201)
def add_incident_note(
    identifier: int,
    payload: NoteCreate,
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    add_note(identifier, admin["username"], payload.body, db_path(request))
    return {"ok": True}


@router.patch("/{identifier}", response_model=dict[str, Any])
def assign(
    identifier: int,
    payload: AssigneeUpdate,
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    set_assignee(identifier, payload.assignee, admin["username"], db_path(request))
    return {"assignee": payload.assignee}


@router.get("/{identifier}/export", response_model=str)
def export(
    identifier: int,
    request: Request,
    format: str = "md",
    _user: dict[str, Any] = Depends(current_user),
) -> str:
    incident = get_incident(identifier, db_path(request))
    if incident is None:
        raise ApiError(404, "not_found", "incident not found")
    rendered = render_incident(incident_report(incident), format)
    return rendered.decode("utf-8", errors="replace") if isinstance(rendered, bytes) else rendered
