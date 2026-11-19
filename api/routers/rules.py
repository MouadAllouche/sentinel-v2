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


def _range(payload: dict[str, Any]) -> tuple[datetime, datetime]:
    try:
        until = datetime.fromisoformat(payload.get("until") or datetime.now(UTC).isoformat())
        start = (
            datetime.fromisoformat(payload["since"])
            if payload.get("since")
            else until - timedelta(days=7)
        )
    except (ValueError, TypeError) as exc:
        raise ApiError(
            422, "validation_error", "since and until must be ISO-8601 timestamps"
        ) from exc
    if start > until:
        raise ApiError(422, "validation_error", "since must not be after until")
    if until - start > timedelta(days=30):
        raise ApiError(422, "validation_error", "backtest range exceeds 30 days")
    return start, until


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
    from core.events import (
        EVENT_TYPES,
        OPTIONAL_FIELDS,
        REQUIRED_FIELDS,
        VALID_SEVERITIES,
    )
    from core.mitre import mitre_table

    fields = [
        {"name": name, "type": "time" if name == "timestamp" else "text"}
        for name in (*REQUIRED_FIELDS, *OPTIONAL_FIELDS)
    ]
    fields.extend(
        [
            {"name": "details.*", "type": "text"},
            {"name": "enrichment.*", "type": "text"},
        ]
    )
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
        "fields": fields,
        "kinds": [
            "threshold",
            "sequence",
            "new_value",
            "field_match",
            "baseline_metric",
            "incident_meta",
        ],
        "severities": list(VALID_SEVERITIES),
        "window_modes": ["sliding", "fixed"],
        "fixed_alignments": ["minute", "hour", "day"],
        "aggregates": ["count", "distinct_count"],
        "mitre": [
            {"id": identifier, "name": value["name"], "label": value.get("label", identifier)}
            for identifier, value in sorted(mitre_table().items())
        ],
        "limits": {
            "max_tiers": 10,
            "min_window_seconds": 10,
            "max_window_seconds": 2_592_000,
            "max_condition_depth": 4,
        },
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
    start, until = _range(payload)
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
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return [rule.model_dump() for rule in list_rules(db_path=db_path(request))]


@router.post("/import", response_model=dict[str, Any])
def import_rules(
    payload: dict[str, Any],
    request: Request,
    _admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    definitions = payload.get("rules", [])
    if not isinstance(definitions, list):
        raise ApiError(422, "validation_error", "rules must be a list")
    if len(definitions) > 100:
        raise ApiError(422, "validation_error", "import is limited to 100 rules")
    created: list[str] = []
    errors: list[dict[str, Any]] = []
    for index, definition in enumerate(definitions):
        if not isinstance(definition, dict):
            errors.append(
                {"index": index, "path": f"rules[{index}]", "message": "must be an object"}
            )
            continue
        try:
            validate_rule(definition)
            if get_rule(str(definition.get("id")), db_path(request)) is not None:
                errors.append(
                    {
                        "index": index,
                        "path": f"rules[{index}].id",
                        "message": "a rule with this id already exists",
                    }
                )
                continue
        except RuleValidationError as exc:
            errors.extend(
                {
                    "index": index,
                    "path": f"rules[{index}].{error['path']}",
                    "message": error["message"],
                }
                for error in exc.errors
            )
            continue
        created.append(create_rule(definition, _admin["username"], db_path(request)))
    return {"created": created, "errors": errors}


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


@router.post("/{identifier}/versions/{version}/restore", response_model=dict[str, Any])
def restore_version(
    identifier: str,
    version: int,
    request: Request,
    _admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    from storage.rules_repository import restore_rule_version

    try:
        new_version = restore_rule_version(
            identifier, version, _admin["username"], db_path(request)
        )
    except RuleValidationError as exc:
        raise ApiError(422, "validation_error", "stored version is invalid", exc.errors) from exc
    except ValueError as exc:
        raise ApiError(404, "not_found", str(exc)) from exc
    return {"version": new_version}


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
    start, until = _range(payload)
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
