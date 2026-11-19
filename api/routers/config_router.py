"""Editable configuration endpoints (severity, allowlist, drift, notifications, settings)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from api.deps import ApiError, admin_user, current_user, db_path
from api.schemas import BaselineAccept
from core.retention import DEFAULT_POLICY, plan_prune
from storage.baseline_repository import get_baseline_series, list_baselines
from storage.drift_repository import (
    add_monitored_path,
    delete_monitored_path,
    get_baseline_snapshot,
    get_previous_snapshot,
    list_monitored_paths,
    list_snapshot_history,
    reset_monitored_path,
    update_monitored_path,
)
from storage.notification_repository import (
    add_channel,
    delete_channel,
    list_channels,
    list_notifications,
    update_channel,
)
from storage.repositories import get_setting, set_setting
from storage.retention_repository import apply_prune, retention_stats
from storage.severity_repository import (
    add_allowlist_entry,
    create_override,
    delete_allowlist_entry,
    delete_override,
    get_allowlist_entries,
    get_defaults,
    get_overrides,
    reset_all_defaults,
    reset_default,
    reset_override,
    set_default,
    update_allowlist_entry,
    update_override,
)

router = APIRouter(prefix="/api", tags=["configuration"])


@router.get("/severity/defaults", response_model=dict[str, Any])
def defaults(request: Request, _user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {key: vars(value) for key, value in get_defaults(db_path(request)).items()}


@router.put("/severity/defaults/{event_type}", response_model=dict[str, Any])
def set_event_default(
    event_type: str,
    payload: dict[str, Any],
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    set_default(
        event_type,
        payload["severity"],
        int(payload["points"]),
        enabled=bool(payload.get("enabled", True)),
        actor=admin["username"],
        db_path=db_path(request),
    )
    return {"event_type": event_type}


@router.post("/severity/defaults/{event_type}/reset", response_model=dict[str, Any])
def reset_event_default(
    event_type: str, request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    reset_default(event_type, admin["username"], db_path(request))
    return {"ok": True}


@router.post("/severity/defaults/reset", response_model=dict[str, Any])
def reset_all_event_defaults(
    request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    reset_all_defaults(admin["username"], db_path(request))
    return {"ok": True}


@router.get("/severity/overrides", response_model=list[dict[str, Any]])
def overrides(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return [vars(item) for item in get_overrides(db_path(request))]


@router.get("/allowlist", response_model=list[dict[str, Any]])
def allowlist(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return [vars(item) for item in get_allowlist_entries(db_path(request))]


@router.post("/allowlist", response_model=dict[str, Any], status_code=201)
def add_allowlist(
    payload: dict[str, Any], request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    identifier = add_allowlist_entry(payload, admin["username"], db_path(request))
    return {"id": identifier}


@router.delete("/allowlist/{identifier}", response_model=dict[str, Any])
def remove_allowlist(
    identifier: int, request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    delete_allowlist_entry(identifier, admin["username"], db_path(request))
    return {"ok": True}


@router.get("/baselines", response_model=list[dict[str, Any]])
def baselines(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return [vars(item) for item in list_baselines(db_path(request))]


@router.get("/baselines/series", response_model=list[dict[str, Any]])
def baseline_series(
    metric: str,
    subject: str,
    request: Request,
    since: str | None = None,
    _user: dict[str, Any] = Depends(current_user),
) -> list[dict[str, Any]]:
    return get_baseline_series(metric, subject, since=since, db_path=db_path(request))


@router.get("/drift/paths", response_model=list[dict[str, Any]])
def drift_paths(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return [vars(item) for item in list_monitored_paths(db_path(request))]


@router.post("/drift/paths", response_model=dict[str, Any], status_code=201)
def add_path(
    payload: dict[str, Any], request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    identifier = add_monitored_path(
        payload, admin["username"], db_path(request), allow_custom_paths=True
    )
    return {"id": identifier}


@router.post("/drift/paths/{identifier}/reset", response_model=dict[str, Any])
def reset_path(
    identifier: int, request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    reset_monitored_path(identifier, admin["username"], db_path(request))
    return {"ok": True}


@router.post("/drift/accept", response_model=dict[str, Any])
def accept(
    payload: BaselineAccept, request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    path = next(
        (item for item in list_monitored_paths(db_path(request)) if item.path == payload.path), None
    )
    if path is None:
        raise ApiError(404, "not_found", "monitored path not found")
    from engine.drift import accept_baseline

    accept_baseline(path.id, admin["username"], payload.reason, db_path(request))
    return {"ok": True}


@router.get("/notifications/channels", response_model=list[dict[str, Any]])
def channels(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return [vars(item) for item in list_channels(db_path(request))]


def _validate_channel_config(config: Any) -> None:
    import re

    if not isinstance(config, dict):
        raise ApiError(422, "validation_error", "config must be an object")
    for key, value in config.items():
        secret_field = key.endswith("_env") or key in {"secret_env", "token_env", "password_env"}
        if secret_field and (
            not isinstance(value, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", value)
        ):
            raise ApiError(
                422,
                "validation_error",
                "secrets must be environment variable names",
                [
                    {
                        "path": f"config.{key}",
                        "message": "use an uppercase environment variable name",
                    }
                ],
            )


@router.post("/notifications/channels", response_model=dict[str, Any], status_code=201)
def create_channel(
    payload: dict[str, Any], request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    _validate_channel_config(payload.get("config", {}))
    identifier = add_channel(payload, admin["username"], db_path(request))
    return {"id": identifier}


@router.put("/notifications/channels/{identifier}", response_model=dict[str, Any])
def edit_channel(
    identifier: int,
    payload: dict[str, Any],
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    if "config" in payload:
        _validate_channel_config(payload["config"])
    update_channel(identifier, payload, admin["username"], db_path(request))
    return {"id": identifier}


@router.delete("/notifications/channels/{identifier}", response_model=dict[str, Any])
def remove_channel(
    identifier: int, request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    delete_channel(identifier, admin["username"], db_path(request))
    return {"ok": True}


@router.post("/notifications/channels/{identifier}/test", response_model=dict[str, Any])
def test_channel(
    identifier: int, request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    from core.notifications.models import Notification
    from engine.notifier import _transport, deliver

    channel = next(
        (item for item in list_channels(db_path(request)) if item.id == identifier), None
    )
    if channel is None:
        raise ApiError(404, "not_found", "channel not found")
    message = Notification(
        kind="test",
        incident_id=0,
        severity="low",
        title="Sentinel test message",
        score=0,
        reasons=[],
        target=str(channel.config.get("url", "")),
    )
    transport = _transport(channel)
    ok = transport is not None and deliver(transport, message, attempts=1, backoff_seconds=0)
    return {"ok": ok}


@router.get("/notifications/log", response_model=list[dict[str, Any]])
def notification_log(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    return list_notifications(db_path(request))


@router.get("/risk/thresholds", response_model=dict[str, Any])
def risk_thresholds(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    return get_setting("risk.severity_thresholds", db_path(request)) or {}


@router.put("/risk/thresholds", response_model=dict[str, Any])
def set_risk_thresholds(
    payload: dict[str, Any], request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    from core.risk_scoring import validate_thresholds

    try:
        validate_thresholds(payload)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    set_setting(
        "risk.severity_thresholds", payload, updated_by=admin["username"], db_path=db_path(request)
    )
    return payload


@router.get("/settings/retention", response_model=dict[str, Any])
def retention(request: Request, _user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return get_setting("retention", db_path(request)) or DEFAULT_POLICY


@router.put("/settings/retention", response_model=dict[str, Any])
def update_retention(
    payload: dict[str, Any], request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    from core.retention import validate_policy

    try:
        validate_policy(payload)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    set_setting("retention", payload, updated_by=admin["username"], db_path=db_path(request))
    return payload


@router.post("/retention/dry-run", response_model=dict[str, Any])
def retention_dry_run(
    request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    policy = get_setting("retention", db_path(request)) or DEFAULT_POLICY
    plan = plan_prune(policy, retention_stats(db_path(request), policy), datetime.now(UTC))
    return apply_prune(plan, db_path(request), dry_run=True, actor=admin["username"], policy=policy)


@router.post("/retention/apply", response_model=dict[str, Any])
def retention_apply(
    request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    policy = get_setting("retention", db_path(request)) or DEFAULT_POLICY
    plan = plan_prune(policy, retention_stats(db_path(request), policy), datetime.now(UTC))
    return apply_prune(
        plan, db_path(request), dry_run=False, actor=admin["username"], policy=policy
    )


@router.post("/severity/overrides/test", response_model=dict[str, Any])
def test_override(
    payload: dict[str, Any], request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    """Explain which default/override would apply to a sample event (no writes)."""
    from core.severity import resolve_severity

    event = payload.get("event")
    if not isinstance(event, dict):
        raise ApiError(422, "validation_error", "event must be an object")
    severity, source = resolve_severity(
        event,
        get_defaults(db_path(request)),
        get_overrides(db_path(request)),
    )
    return {"severity": severity, "severity_source": source}


@router.post("/severity/overrides", response_model=dict[str, Any], status_code=201)
def add_override(
    payload: dict[str, Any], request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    return {"id": create_override(payload, admin["username"], db_path(request))}


@router.put("/severity/overrides/{identifier}", response_model=dict[str, Any])
def edit_override(
    identifier: str,
    payload: dict[str, Any],
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    update_override(identifier, payload, admin["username"], db_path(request))
    return {"id": identifier}


@router.delete("/severity/overrides/{identifier}", response_model=dict[str, Any])
def remove_override(
    identifier: str, request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    delete_override(identifier, admin["username"], db_path(request))
    return {"ok": True}


@router.post("/severity/overrides/{identifier}/reset", response_model=dict[str, Any])
def restore_override(
    identifier: str, request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    reset_override(identifier, admin["username"], db_path(request))
    return {"ok": True}


@router.post("/severity/overrides/reorder", response_model=dict[str, Any])
def reorder_overrides(
    payload: dict[str, Any], request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    for identifier, priority in payload.get("order", {}).items():
        update_override(identifier, {"priority": priority}, admin["username"], db_path(request))
    return {"ok": True}


@router.get("/risk/decay", response_model=dict[str, Any])
def risk_decay(request: Request, _user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return get_setting("risk.recency_decay", db_path(request)) or {
        "enabled": False,
        "half_life_hours": 72,
    }


@router.put("/risk/decay", response_model=dict[str, Any])
def set_risk_decay(
    payload: dict[str, Any], request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    set_setting(
        "risk.recency_decay", payload, updated_by=admin["username"], db_path=db_path(request)
    )
    return payload


@router.put("/allowlist/{identifier}", response_model=dict[str, Any])
def edit_allowlist(
    identifier: int,
    payload: dict[str, Any],
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    update_allowlist_entry(identifier, payload, admin["username"], db_path(request))
    return {"id": identifier}


@router.get("/allowlist/stats", response_model=dict[str, Any])
def allowlist_stats(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    entries = get_allowlist_entries(db_path(request))
    return {
        "total": len(entries),
        "suppress_alerts": sum(entry.scope == "suppress_alerts" for entry in entries),
    }


@router.put("/drift/paths/{identifier}", response_model=dict[str, Any])
def edit_path(
    identifier: int,
    payload: dict[str, Any],
    request: Request,
    admin: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    update_monitored_path(identifier, payload, admin["username"], db_path(request))
    return {"id": identifier}


@router.delete("/drift/paths/{identifier}", response_model=dict[str, Any])
def remove_path(
    identifier: int, request: Request, admin: dict[str, Any] = Depends(admin_user)
) -> dict[str, Any]:
    delete_monitored_path(identifier, admin["username"], db_path(request))
    return {"ok": True}


@router.get("/drift/status", response_model=list[dict[str, Any]])
def drift_status(
    request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    result = []
    for item in list_monitored_paths(db_path(request)):
        current = get_previous_snapshot(item.path, db_path(request))
        baseline = get_baseline_snapshot(item.path, db_path(request))
        result.append(
            {
                "id": item.id,
                "path": item.path,
                "enabled": item.enabled,
                "metadata_only": item.metadata_only,
                "baseline_status": "clean"
                if current and baseline and current.get("sha256") == baseline.get("sha256")
                else "drifted",
                "warnings": current.get("warnings", []) if current else [],
            }
        )
    return result


@router.get("/drift/paths/{identifier}/history", response_model=list[dict[str, Any]])
def path_history(
    identifier: int, request: Request, _user: dict[str, Any] = Depends(current_user)
) -> list[dict[str, Any]]:
    item = next(
        (item for item in list_monitored_paths(db_path(request)) if item.id == identifier), None
    )
    if item is None:
        raise ApiError(404, "not_found", "monitored path not found")
    return list_snapshot_history(item.path, db_path=db_path(request))


@router.post("/drift/check", response_model=dict[str, Any])
def drift_check(request: Request, admin: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    from engine.drift import check_drift

    return check_drift(db_path(request)).__dict__
