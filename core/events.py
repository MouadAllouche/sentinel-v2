"""Canonical event definition and validation.

This module is pure: it holds the taxonomy and type rules shared by collectors,
storage and the API. It never reads system state, the clock or the database.
"""

from __future__ import annotations

from datetime import datetime

__all__ = [
    "EVENT_TYPES",
    "OPTIONAL_FIELDS",
    "REQUIRED_FIELDS",
    "SEVERITY_ORDER",
    "SOURCES",
    "VALID_SEVERITIES",
    "max_severity",
    "severity_at_least",
    "validate_event",
]

REQUIRED_FIELDS: tuple[str, ...] = (
    "timestamp",
    "source",
    "event_type",
    "severity",
    "description",
)

OPTIONAL_FIELDS: tuple[str, ...] = (
    "username",
    "source_ip",
    "local_ip",
    "destination_ip",
    "destination_port",
    "connection_status",
    "process_id",
    "process_name",
    "user_permissions",
    "file_path",
    "details",
    "enrichment",
    "severity_source",
)

VALID_SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")

EVENT_TYPES: tuple[str, ...] = (
    "failed_login",
    "successful_login",
    "invalid_user",
    "preauth_disconnect",
    "sudo_command",
    "su_command",
    "user_created",
    "user_deleted",
    "group_member_added",
    "password_changed",
    "permission_change",
    "network_connection",
    "new_listening_port",
    "process_started",
    "suspicious_process",
    "package_installed",
    "package_removed",
    "config_drift",
    "anomaly",
    "rule_triggered",
    "system_info",
)

SOURCES: tuple[str, ...] = (
    "auth_log",
    "journald",
    "dpkg",
    "network",
    "listening",
    "process",
    "filesystem",
    "system",
    "baseline",
    "rules",
)

SEVERITY_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}

_OPTIONAL_TEXT_FIELDS: tuple[str, ...] = (
    "username",
    "source_ip",
    "local_ip",
    "destination_ip",
    "connection_status",
    "process_name",
    "file_path",
    "severity_source",
)


def validate_event(event: object) -> bool:
    """Return True when ``event`` satisfies the canonical event contract.

    Naive timestamps are tolerated here; ``normalize_event`` produces UTC-aware
    values and storage rejects naive ones. Unknown keys are ignored so records
    that carry extra bookkeeping columns remain valid.
    """
    if not isinstance(event, dict):
        return False
    for field in REQUIRED_FIELDS:
        if field not in event:
            return False
    timestamp = event["timestamp"]
    if not isinstance(timestamp, str):
        return False
    try:
        datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    for field in ("source", "event_type", "description"):
        value = event[field]
        if not isinstance(value, str) or not value.strip():
            return False
    if event["severity"] not in VALID_SEVERITIES:
        return False
    for field in _OPTIONAL_TEXT_FIELDS:
        if field in event and not isinstance(event[field], str):
            return False
    for field in ("destination_port", "process_id"):
        if field in event:
            value = event[field]
            if isinstance(value, bool) or not isinstance(value, int):
                return False
    for field in ("details", "enrichment"):
        if field in event and not isinstance(event[field], dict):
            return False
    if "user_permissions" in event:
        permissions = event["user_permissions"]
        if not isinstance(permissions, dict):
            return False
        for side in ("before", "after"):
            values = permissions.get(side)
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                return False
    return True


def _severity_rank(severity: object) -> int:
    try:
        return SEVERITY_ORDER[severity]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"invalid severity: {severity!r}") from exc


def max_severity(a: str, b: str) -> str:
    """Return the more severe of two severity labels."""
    return a if _severity_rank(a) >= _severity_rank(b) else b


def severity_at_least(a: str, b: str) -> bool:
    """Return True when severity ``a`` is at least as severe as ``b``."""
    return _severity_rank(a) >= _severity_rank(b)
