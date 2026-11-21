"""Incident endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response

from api.deps import ApiError, admin_user, current_user, db_path
from api.schemas import (
    AssigneeUpdate,
    BulkStatusChange,
    IncidentOut,
    IncidentPage,
    NoteCreate,
    StatusChange,
)
from core.correlation import Component
from core.export import incident_report, render_incident
from core.incidents import apply_status_transition
from core.normalizer import compute_event_hash
from core.timeline import build_timeline, component_with_links, explain_incident
from storage.incident_repository import (
    add_note,
    get_incident,
    list_incidents_page,
    list_notes,
    list_status_history,
    set_assignee,
    set_incident_status,
)
from storage.repositories import get_events_by_ids, list_audit
from storage.risk_repository import get_assessment
from storage.rules_repository import list_findings

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


def _component(
    incident: dict[str, Any], request: Request
) -> tuple[Component, list[dict[str, Any]]]:
    events = list(get_events_by_ids(incident.get("event_ids", []), db_path(request)).values())
    for event in events:
        event.setdefault("event_hash", compute_event_hash(event))
    # Stored incidents do not persist Link rows; recompute them so explanations
    # and timeline relation connectors contain every strong/weak reason.
    return component_with_links(events, datetime.now(UTC)), events


def _findings_for(incident: dict[str, Any], request: Request) -> list[dict[str, Any]]:
    """Normalise stored finding rows into the shape the timeline/explanation expect."""
    event_ids = set(incident.get("event_ids", []))
    findings = []
    for item in list_findings({}, limit=500, db_path=db_path(request)):
        evidence = [int(value) for value in json.loads(item.get("evidence_event_ids_json") or "[]")]
        if not set(evidence) & event_ids:
            continue
        findings.append(
            {
                **item,
                "evidence_event_ids": evidence,
                "tier_label": f"Tier {item.get('tier_index', 0)}",
                "explanation": (
                    f"{item.get('observed', 0)} matching events from {item.get('group_key', '')} "
                    f"within {item.get('window_start', '')}..{item.get('window_end', '')} "
                    f"reached {item.get('severity', 'low')} severity"
                ),
            }
        )
    return findings


@router.get("", response_model=IncidentPage)
def incidents(
    request: Request,
    status: list[str] | None = Query(default=None),
    severity: list[str] | None = Query(default=None),
    since: str | None = None,
    until: str | None = None,
    assignee: str | None = None,
    search: str | None = None,
    needs_attention: bool | None = None,
    sort: str = "risk",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    _user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    if sort not in {"risk", "recent"}:
        raise ApiError(422, "validation_error", "sort must be risk or recent")
    filters = {
        key: value
        for key, value in {
            "status": status,
            "severity": severity,
            "since": since,
            "until": until,
            "assignee": assignee,
            "search": search,
            "needs_attention": needs_attention,
        }.items()
        if value is not None
    }
    return list_incidents_page(
        filters, cursor=cursor, limit=limit, sort=sort, db_path=db_path(request)
    )


@router.post("/bulk-status", response_model=dict[str, Any])
def bulk_status(
    payload: BulkStatusChange, request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    ids = list(dict.fromkeys(payload.ids))
    if not ids or len(ids) > 500:
        raise ApiError(422, "validation_error", "ids must contain 1..500 incidents")
    for identifier in ids:
        incident = get_incident(identifier, db_path(request))
        if incident is None:
            raise ApiError(404, "not_found", f"incident {identifier} not found")
        try:
            apply_status_transition(str(incident["status"]), payload.status, payload.reason)
        except ValueError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
        set_incident_status(
            identifier,
            str(incident["status"]),
            payload.status,
            admin["username"],
            payload.reason,
            db_path(request),
        )
    return {"updated": len(ids)}


@router.get("/{identifier}", response_model=IncidentOut)
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
    component, _events = _component(incident, request)
    return build_timeline(component, _events, component.links, _findings_for(incident, request))


@router.get("/{identifier}/explanation", response_model=dict[str, Any])
def explanation(
    identifier: int, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    incident = get_incident(identifier, db_path(request))
    if incident is None:
        raise ApiError(404, "not_found", "incident not found")
    component, events = _component(incident, request)
    return explain_incident(component, events, _findings_for(incident, request))


@router.get("/{identifier}/history", response_model=dict[str, Any])
def history(
    identifier: int, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    if get_incident(identifier, db_path(request)) is None:
        raise ApiError(404, "not_found", "incident not found")
    audit = [
        item
        for item in list_audit({"target_type": "incident"}, limit=500, db_path=db_path(request))[
            "items"
        ]
        if item.get("target_id") == str(identifier)
    ]
    return {
        "history": list_status_history(identifier, db_path(request)),
        "audit": audit,
    }


@router.get("/{identifier}/graph", response_model=dict[str, Any])
def graph(
    identifier: int, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    incident = get_incident(identifier, db_path(request))
    if incident is None:
        raise ApiError(404, "not_found", "incident not found")
    component, events = _component(incident, request)
    by_id = {int(event.get("id", 0)): event for event in events}

    def entities(identifier: int) -> list[str]:
        event = by_id.get(identifier)
        if event is None:
            return []
        return [
            f"{key}:{event[key]}"
            for key in ("source_ip", "username", "process_name", "file_path")
            if event.get(key)
        ]

    counts: dict[str, int] = {}
    for event in events:
        for node in entities(int(event.get("id", 0))):
            counts[node] = counts.get(node, 0) + 1
    edges = []
    for link in component.links:
        first, second = entities(int(link.a)), entities(int(link.b))
        if not first or not second:
            continue
        edges.append(
            {
                "a": first[0],
                "b": second[0],
                "strength": link.strength,
                "reason": link.reason,
            }
        )
    return {
        "nodes": [
            {
                "id": node,
                "kind": node.split(":", 1)[0],
                "value": node.split(":", 1)[1],
                "count": count,
            }
            for node, count in sorted(counts.items())
        ],
        "edges": edges,
    }


@router.post("/{identifier}/status", response_model=dict[str, Any], status_code=200)
def status(
    identifier: int,
    payload: StatusChange,
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    incident = get_incident(identifier, db_path(request))
    if incident is None:
        raise ApiError(404, "not_found", "incident not found")
    if payload.updated_at and str(incident.get("updated_at")) != payload.updated_at:
        raise ApiError(409, "conflict", "Incident changed, reload")
    try:
        apply_status_transition(str(incident["status"]), payload.status, payload.reason)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    set_incident_status(
        identifier,
        str(incident["status"]),
        payload.status,
        admin["username"],
        payload.reason,
        db_path(request),
    )
    updated = get_incident(identifier, db_path(request))
    return {
        "status": payload.status,
        "updated_at": updated["updated_at"] if updated else None,
    }


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


@router.get("/{identifier}/export")
def export(
    identifier: int,
    request: Request,
    format: str = "md",
    _user: dict[str, Any] = Depends(current_user),
) -> Response:
    incident = get_incident(identifier, db_path(request))
    if incident is None:
        raise ApiError(404, "not_found", "incident not found")
    if format not in {"md", "json", "pdf"}:
        raise ApiError(422, "validation_error", "format must be md, json or pdf")
    component, events = _component(incident, request)
    assessment = get_assessment("incident", identifier, db_path(request))
    reasons = list((assessment or {}).get("reasons", []))
    rendered = render_incident(
        incident_report(
            incident,
            timeline=build_timeline(
                component, events, component.links, _findings_for(incident, request)
            ),
            reasons=reasons,
            notes=list_notes(identifier, db_path(request)),
        ),
        format,
    )
    media = {
        "md": "text/markdown; charset=utf-8",
        "json": "application/json",
        "pdf": "application/pdf",
    }[format]
    content = rendered if isinstance(rendered, bytes) else rendered.encode("utf-8")
    return Response(
        content=content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="sentinel-incident-{identifier}.{format}"'
        },
    )
