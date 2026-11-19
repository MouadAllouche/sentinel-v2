"""Rule endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request

from api.deps import ApiError, admin_user, current_user, db_path
from api.schemas import RuleDefinition
from core.rules.backtest import backtest_rule
from core.rules.models import RuleValidationError, validate_rule
from storage.rules_repository import (
    create_rule,
    get_events_for_rules,
    get_rule,
    get_rule_versions,
    list_findings,
    list_rules,
    reset_rule,
    set_rule_enabled,
    update_rule,
)

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _deadline() -> Any:
    """Cooperative 30-second deadline for backtests (no clock reads in core)."""
    import time

    end = time.monotonic() + 30
    return lambda: time.monotonic() > end


def _definition_model(data: dict[str, Any]) -> dict[str, Any]:
    try:
        return validate_rule(data)[0].model_dump()
    except RuleValidationError as exc:
        raise ApiError(422, "validation_error", "invalid rule", exc.errors) from exc


@router.get("", response_model=list[dict[str, Any]])
def rules(request: Request, _user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    return [rule.model_dump() for rule in list_rules(db_path=db_path(request))]


@router.get("/findings", response_model=list[dict[str, Any]])
def findings(
    request: Request, rule_id: str | None = None, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return list_findings({"rule_id": rule_id} if rule_id else {}, db_path=db_path(request))


@router.get("/schema", response_model=dict[str, Any])
def schema(_user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    from core.conditions import OPS
    from core.events import EVENT_TYPES

    return {
        "ops": sorted(OPS),
        "event_types": list(EVENT_TYPES),
        "group_by": [
            "source_ip",
            "username",
            "process_name",
            "destination_ip",
            "file_path",
            "source",
        ],
    }


@router.post("/validate", response_model=dict[str, Any])
def validate(
    payload: RuleDefinition, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    try:
        rule, warnings = validate_rule(payload.definition)
        return {"rule": rule.model_dump(), "warnings": warnings}
    except RuleValidationError as exc:
        raise ApiError(422, "validation_error", "invalid rule", exc.errors) from exc


@router.post("/preview", response_model=dict[str, Any])
def preview(
    payload: dict[str, Any], request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    definition = payload.get("definition")
    if not isinstance(definition, dict):
        raise ApiError(422, "validation_error", "definition is required")
    rule, _warnings = validate_rule(definition)
    until = datetime.fromisoformat(payload.get("until") or datetime.now(UTC).isoformat())
    start = (
        datetime.fromisoformat(payload["since"])
        if payload.get("since")
        else until - timedelta(days=7)
    )
    if until - start > timedelta(days=30):
        raise ApiError(422, "validation_error", "backtest range exceeds 30 days")
    events = get_events_for_rules(start.isoformat(), db_path(request))
    result = backtest_rule(
        rule, events, start.isoformat(), until.isoformat(), should_stop=_deadline()
    )
    return {
        "total_findings": result.total_findings,
        "by_severity": result.by_severity,
        "groups": result.top_groups,
        "noise_per_day": result.noise_per_day,
        "samples": result.samples,
    }


@router.post("", response_model=dict[str, Any])
def create(
    payload: dict[str, Any], request: Request, _admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    definition = payload.get("definition", payload)
    if not isinstance(definition, dict):
        raise ApiError(422, "validation_error", "definition must be an object")
    identifier = create_rule(definition, _admin["username"], db_path(request))
    return {"id": identifier, "warnings": []}


@router.get("/export", response_model=list[dict[str, Any]])
def export_rules(
    _user: dict[str, Any] = Depends(current_user),
) -> list[dict[str, Any]]:
    from core.rules.defaults import DEFAULT_RULES

    return [definition for definition in DEFAULT_RULES]


@router.post("/import", response_model=dict[str, Any])
def import_rules(
    payload: dict[str, Any],
    request: Request,
    _admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    definitions = payload.get("rules", [])
    if not isinstance(definitions, list):
        raise ApiError(422, "validation_error", "rules must be a list")
    created = []
    for definition in definitions:
        if not isinstance(definition, dict):
            raise ApiError(422, "validation_error", "each rule must be an object")
        created.append(create_rule(definition, _admin["username"], db_path(request)))
    return {"created": created}


@router.get("/{identifier}", response_model=dict[str, Any])
def show(
    identifier: str, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    rule = get_rule(identifier, db_path(request))
    if rule is None:
        raise ApiError(404, "not_found", "rule not found")
    return rule.model_dump()


@router.put("/{identifier}", response_model=dict[str, Any])
def update(
    identifier: str,
    payload: dict[str, Any],
    request: Request,
    _admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    rule = get_rule(identifier, db_path(request))
    if rule is None:
        raise ApiError(404, "not_found", "rule not found")
    definition = payload.get("definition", payload)
    if not isinstance(definition, dict):
        raise ApiError(422, "validation_error", "definition must be an object")
    update_rule(identifier, definition, _admin["username"], db_path(request))
    return {"rule": get_rule(identifier, db_path(request)).model_dump(), "warnings": []}  # type: ignore[union-attr]


@router.delete("/{identifier}", response_model=dict[str, Any])
def delete(
    identifier: str, request: Request, _admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    from storage.rules_repository import delete_rule

    delete_rule(identifier, _admin["username"], db_path(request))
    return {"ok": True}


@router.post("/{identifier}/enable", response_model=dict[str, Any])
def enable(
    identifier: str, request: Request, _admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    set_rule_enabled(identifier, True, _admin["username"], db_path(request))
    return {"ok": True}


@router.post("/{identifier}/disable", response_model=dict[str, Any])
def disable(
    identifier: str, request: Request, _admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    set_rule_enabled(identifier, False, _admin["username"], db_path(request))
    return {"ok": True}


@router.post("/{identifier}/reset", response_model=dict[str, Any])
def reset(
    identifier: str, request: Request, _admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    reset_rule(identifier, _admin["username"], db_path(request))
    return {"ok": True}


@router.get("/{identifier}/versions", response_model=list[dict[str, Any]])
def versions(
    identifier: str, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return get_rule_versions(identifier, db_path(request))


@router.post("/{identifier}/backtest", response_model=dict[str, Any])
def backtest(
    identifier: str,
    payload: dict[str, Any],
    request: Request,
    _user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    rule = get_rule(identifier, db_path(request))
    if rule is None:
        raise ApiError(404, "not_found", "rule not found")
    until = datetime.fromisoformat(payload.get("until") or datetime.now(UTC).isoformat())
    start = (
        datetime.fromisoformat(payload["since"])
        if payload.get("since")
        else until - timedelta(days=7)
    )
    if until - start > timedelta(days=30):
        raise ApiError(422, "validation_error", "backtest range exceeds 30 days")
    result = backtest_rule(
        rule,
        get_events_for_rules(start.isoformat(), db_path(request)),
        start.isoformat(),
        until.isoformat(),
        should_stop=_deadline(),
    )
    return {
        "total_findings": result.total_findings,
        "by_severity": result.by_severity,
        "groups": result.top_groups,
        "noise_per_day": result.noise_per_day,
        "samples": result.samples,
    }
