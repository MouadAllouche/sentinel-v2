"""Normalize raw collector output into the canonical event format.

Pure: no database, filesystem or network access. Timestamps are converted with
``core.timeutil`` (the only clock entry point is ``utc_now``). Unknown fields
are dropped and sensitive fields are never invented here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, NotRequired, TypedDict

from core.events import OPTIONAL_FIELDS, REQUIRED_FIELDS, validate_event
from core.timeutil import to_utc_iso

__all__ = [
    "NormalizedEvent",
    "canonicalize",
    "compute_event_hash",
    "normalize_event",
]


class NormalizedEvent(TypedDict):
    """Typing-only view of a normalized event."""

    timestamp: str
    source: str
    event_type: str
    severity: str
    description: str
    username: NotRequired[str]
    source_ip: NotRequired[str]
    local_ip: NotRequired[str]
    destination_ip: NotRequired[str]
    destination_port: NotRequired[int]
    connection_status: NotRequired[str]
    process_id: NotRequired[int]
    process_name: NotRequired[str]
    user_permissions: NotRequired[dict[str, list[str]]]
    file_path: NotRequired[str]
    details: NotRequired[dict[str, Any]]
    enrichment: NotRequired[dict[str, Any]]
    severity_source: NotRequired[str]


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "date"),
    "source": ("source", "source_system"),
    "event_type": ("event_type", "action", "event"),
    "severity": ("severity", "level"),
    "description": ("description", "message"),
    "username": ("username", "user", "account"),
    "source_ip": ("source_ip", "ip", "ip_address"),
    "local_ip": ("local_ip",),
    "destination_ip": ("destination_ip",),
    "destination_port": ("destination_port",),
    "connection_status": ("connection_status",),
    "process_id": ("process_id",),
    "process_name": ("process_name", "process"),
    "user_permissions": ("user_permissions", "permissions"),
    "file_path": ("file_path",),
    "details": ("details",),
    "enrichment": ("enrichment",),
    "severity_source": ("severity_source",),
}

EVENT_TYPE_ALIASES: dict[str, str] = {
    "login_failure": "failed_login",
    "failed_password": "failed_login",
    "login_success": "successful_login",
    "permission_modified": "permission_change",
    "privilege_escalation": "permission_change",
}

_TEXT_FIELDS: frozenset[str] = frozenset(
    field
    for field in (*REQUIRED_FIELDS, *OPTIONAL_FIELDS)
    if field not in {"destination_port", "process_id", "user_permissions", "details", "enrichment"}
)

_HASH_EXCLUDED: frozenset[str] = frozenset({"severity", "severity_source", "enrichment"})


def _resolve(raw: dict[Any, Any], canonical: str) -> Any:
    """Pick the first non-empty value among a canonical name and its aliases."""
    names = FIELD_ALIASES[canonical]
    for name in names:
        if name in raw and raw[name] is not None:
            value = raw[name]
            if not isinstance(value, str) or value.strip():
                return value
    for name in names:
        if name in raw:
            return raw[name]
    return None


def normalize_event(raw: object) -> dict[str, Any]:
    """Return a validated, UTC-aware event built only from known fields.

    Raises ``ValueError`` for non-dict input or for a result that fails
    ``validate_event``.
    """
    if not isinstance(raw, dict):
        raise ValueError("event must be a dict")
    result: dict[str, Any] = {}
    for canonical in (*REQUIRED_FIELDS, *OPTIONAL_FIELDS):
        value = _resolve(raw, canonical)
        if value is None:
            continue
        if canonical in _TEXT_FIELDS and isinstance(value, str):
            value = value.strip()
            if canonical in OPTIONAL_FIELDS and value == "":
                continue
        result[canonical] = value

    event_type = result.get("event_type")
    if isinstance(event_type, str):
        result["event_type"] = EVENT_TYPE_ALIASES.get(event_type, event_type)
    if "timestamp" in result:
        result["timestamp"] = to_utc_iso(result["timestamp"])

    if not validate_event(result):
        raise ValueError("normalized event is invalid")
    return result


def canonicalize(event: Mapping[str, Any]) -> str:
    """Return the canonical JSON used for identity (severity-independent)."""
    if not validate_event(event):
        raise ValueError("cannot canonicalize an invalid event")
    payload = {key: value for key, value in event.items() if key not in _HASH_EXCLUDED}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(event: Mapping[str, Any]) -> str:
    """Return the deterministic SHA-256 identity of an event."""
    return hashlib.sha256(canonicalize(event).encode("utf-8")).hexdigest()
