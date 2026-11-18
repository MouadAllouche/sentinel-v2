"""Data-driven event severity defaults and ordered conditional overrides.

Pure: no database, clock or filesystem. Re-apply and persistence live in
``storage``/``engine``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core.conditions import Condition, evaluate, validate_condition
from core.events import EVENT_TYPES, VALID_SEVERITIES

__all__ = [
    "DEFAULT_OVERRIDES",
    "DEFAULT_TYPE_DEFAULTS",
    "Override",
    "TypeDefault",
    "resolve_severity",
    "validate_defaults",
    "validate_overrides",
]


@dataclass(frozen=True)
class TypeDefault:
    event_type: str
    severity: str
    points: int
    description: str = ""
    default_severity: str | None = None
    default_points: int | None = None
    enabled: bool = True


@dataclass(frozen=True)
class Override:
    id: str
    name: str
    priority: int
    conditions: Condition
    severity: str
    enabled: bool = True
    builtin: bool = True
    default_definition_json: str = field(default="", repr=False)


_SEED_DEFAULTS: tuple[tuple[str, str, int], ...] = (
    ("failed_login", "low", 5),
    ("invalid_user", "low", 5),
    ("preauth_disconnect", "low", 0),
    ("successful_login", "low", 0),
    ("sudo_command", "low", 0),
    ("su_command", "low", 0),
    ("user_created", "medium", 10),
    ("user_deleted", "medium", 10),
    ("group_member_added", "medium", 10),
    ("password_changed", "low", 0),
    ("permission_change", "medium", 10),
    ("network_connection", "low", 0),
    ("new_listening_port", "medium", 5),
    ("process_started", "low", 0),
    ("suspicious_process", "high", 15),
    ("package_installed", "low", 0),
    ("package_removed", "low", 0),
    ("config_drift", "medium", 10),
    ("anomaly", "medium", 10),
    ("rule_triggered", "medium", 0),
    ("system_info", "low", 0),
)

DEFAULT_TYPE_DEFAULTS: dict[str, TypeDefault] = {
    event_type: TypeDefault(
        event_type=event_type,
        severity=severity,
        points=points,
        default_severity=severity,
        default_points=points,
    )
    for event_type, severity, points in _SEED_DEFAULTS
}

# Each override carries exactly one severity, so the spec's two-part listening
# override is seeded as two consecutive overrides (D-041).
_OVERRIDE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "failed_login-root",
        "name": "Failed login for root",
        "priority": 1,
        "conditions": {
            "all": [
                {"field": "event_type", "op": "eq", "value": "failed_login"},
                {"field": "username", "op": "eq", "value": "root"},
            ]
        },
        "severity": "medium",
    },
    {
        "id": "sudo-sensitive-command",
        "name": "Sudo of a sensitive command",
        "priority": 2,
        "conditions": {
            "all": [
                {"field": "event_type", "op": "eq", "value": "sudo_command"},
                {
                    "field": "process_name",
                    "op": "in",
                    "value": [
                        "visudo",
                        "passwd",
                        "useradd",
                        "usermod",
                        "userdel",
                        "chmod",
                        "chown",
                        "crontab",
                        "systemctl",
                    ],
                },
            ]
        },
        "severity": "high",
    },
    {
        "id": "drift-world-writable",
        "name": "World-writable sensitive file",
        "priority": 3,
        "conditions": {
            "all": [
                {"field": "event_type", "op": "eq", "value": "config_drift"},
                {"field": "details.flags", "op": "contains", "value": "world_writable"},
            ]
        },
        "severity": "critical",
    },
    {
        "id": "drift-sensitive-content",
        "name": "Drift on sensitive content",
        "priority": 4,
        "conditions": {
            "all": [
                {"field": "event_type", "op": "eq", "value": "config_drift"},
                {"field": "details.sensitivity", "op": "in", "value": ["high", "critical"]},
            ]
        },
        "severity": "high",
    },
    {
        "id": "drift-low-mtime-only",
        "name": "Only modification time changed",
        "priority": 5,
        "conditions": {
            "all": [
                {"field": "event_type", "op": "eq", "value": "config_drift"},
                {"field": "details.only_mtime", "op": "eq", "value": True},
            ]
        },
        "severity": "low",
    },
    {
        "id": "success-from-public-ip",
        "name": "Successful login from public IP",
        "priority": 6,
        "conditions": {
            "all": [
                {"field": "event_type", "op": "eq", "value": "successful_login"},
                {"field": "enrichment.ip_scope", "op": "eq", "value": "public"},
            ]
        },
        "severity": "medium",
    },
    {
        "id": "listening-all-interfaces",
        "name": "Listening on all interfaces",
        "priority": 7,
        "conditions": {
            "all": [
                {"field": "event_type", "op": "eq", "value": "new_listening_port"},
                {"field": "details.bind_scope", "op": "eq", "value": "all_interfaces"},
            ]
        },
        "severity": "medium",
    },
    {
        "id": "listening-loopback",
        "name": "Listening on loopback only",
        "priority": 8,
        "conditions": {
            "all": [
                {"field": "event_type", "op": "eq", "value": "new_listening_port"},
                {"field": "details.bind_scope", "op": "eq", "value": "loopback"},
            ]
        },
        "severity": "low",
    },
)

DEFAULT_OVERRIDES: tuple[Override, ...] = tuple(
    Override(
        id=definition["id"],
        name=definition["name"],
        priority=definition["priority"],
        conditions=validate_condition(definition["conditions"]),
        severity=definition["severity"],
        default_definition_json=json.dumps(definition, sort_keys=True),
    )
    for definition in _OVERRIDE_DEFINITIONS
)


def validate_defaults(defaults: dict[str, TypeDefault]) -> None:
    """Reject invalid severity values and point ranges."""
    for event_type, entry in defaults.items():
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {event_type}")
        if entry.severity not in VALID_SEVERITIES:
            raise ValueError(f"{event_type}: invalid severity {entry.severity!r}")
        if isinstance(entry.points, bool) or not 0 <= entry.points <= 100:
            raise ValueError(f"{event_type}: points must be 0..100")


def validate_overrides(overrides: list[Override] | tuple[Override, ...]) -> None:
    """Enforce unique priorities, valid severities and the 200-entry cap."""
    if len(overrides) > 200:
        raise ValueError("at most 200 severity overrides are allowed")
    priorities = [item.priority for item in overrides]
    if len(set(priorities)) != len(priorities):
        raise ValueError("override priorities must be unique")
    for item in overrides:
        if item.severity not in VALID_SEVERITIES:
            raise ValueError(f"{item.id}: invalid severity {item.severity!r}")


def resolve_severity(
    event: dict[str, Any],
    defaults: dict[str, TypeDefault],
    overrides: list[Override] | tuple[Override, ...],
) -> tuple[str, str]:
    """Return ``(severity, source)`` using first-match overrides then defaults."""
    for override in sorted(overrides, key=lambda item: item.priority):
        if override.enabled and evaluate(override.conditions, event):
            return override.severity, f"override:{override.id}"
    entry = defaults.get(str(event.get("event_type")))
    if entry is not None:
        return entry.severity, "default"
    # D-003: the spec's "fallback" is recorded as "default".
    return "low", "default"
