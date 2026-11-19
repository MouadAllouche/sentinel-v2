"""Built-in seeded rule set. Points are uncalibrated design starting points."""

from __future__ import annotations

import json
from typing import Any

__all__ = ["DEFAULT_RULES"]


def _base(identifier: str, name: str, description: str, event_types: list[str]) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "description": description,
        "kind": "threshold",
        "enabled": True,
        "match": {"event_types": event_types, "conditions": {"all": []}},
        "scope": {"exclude_allowlisted": True},
        "actions": {"create_incident": True, "notify": True, "tags": []},
        "mitre": [],
    }


def _threshold(
    identifier: str,
    name: str,
    description: str,
    event_types: list[str],
    group_by: list[str],
    tiers: list[dict[str, Any]],
    points: list[int],
    mitre: list[str],
    aggregate: dict[str, Any] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    rule = _base(identifier, name, description, event_types)
    rule.update(
        {
            "kind": "threshold",
            "group_by": group_by,
            "aggregate": aggregate or {"type": "count"},
            "window_mode": "sliding",
            "fixed_alignment": None,
            "cooldown_seconds": 900,
            "tiers": [{**tier, "points": point} for tier, point in zip(tiers, points, strict=True)],
            "mitre": mitre,
            "enabled": enabled,
        }
    )
    return rule


def _field_match(
    identifier: str,
    name: str,
    description: str,
    event_types: list[str],
    conditions: dict[str, Any],
    severity: str,
    points: int,
    mitre: list[str],
    group_by: list[str] | None = None,
    cooldown_seconds: int = 0,
) -> dict[str, Any]:
    rule = _base(identifier, name, description, event_types)
    rule.update(
        {
            "kind": "field_match",
            "match": {"event_types": event_types, "conditions": conditions},
            "group_by": group_by or [],
            "severity": severity,
            "points": points,
            "cooldown_seconds": cooldown_seconds,
            "mitre": mitre,
        }
    )
    return rule


_SSH_BRUTEFORCE = _threshold(
    "ssh-bruteforce-by-ip",
    "SSH brute force from one IP",
    "Repeated failed logins from the same source IP",
    ["failed_login", "invalid_user"],
    ["source_ip"],
    [
        {"label": "Repeated failures", "count": 5, "window_seconds": 600, "severity": "medium"},
        {"label": "Sustained attack", "count": 20, "window_seconds": 600, "severity": "high"},
        {"label": "Burst", "count": 50, "window_seconds": 60, "severity": "critical"},
    ],
    [15, 30, 45],
    ["T1110.001"],
)

_SSH_SPRAYING = _threshold(
    "ssh-password-spraying",
    "Password spraying from one IP",
    "Many distinct usernames failing from one source IP",
    ["failed_login"],
    ["source_ip"],
    [{"label": "Spray", "count": 5, "window_seconds": 600, "severity": "high"}],
    [25],
    ["T1110.003"],
    aggregate={"type": "distinct_count", "field": "username"},
)

_SSH_DISTRIBUTED = _threshold(
    "ssh-distributed-single-user",
    "Distributed guessing of one account",
    "Many distinct source IPs failing for one username",
    ["failed_login"],
    ["username"],
    [{"label": "Distributed", "count": 5, "window_seconds": 600, "severity": "high"}],
    [25],
    ["T1110"],
    aggregate={"type": "distinct_count", "field": "source_ip"},
)

_PREAUTH_SCANNING = _threshold(
    "ssh-preauth-scanning",
    "SSH pre-authentication scanning",
    "Many pre-authentication disconnects from one IP",
    ["preauth_disconnect"],
    ["source_ip"],
    [{"label": "Scanning", "count": 20, "window_seconds": 300, "severity": "medium"}],
    [5],
    ["T1046"],
)

_SEQUENCE_SUCCESS = {
    **_base(
        "success-after-failures",
        "Successful login after repeated failures",
        "A successful login shortly after repeated failures",
        ["failed_login"],
    ),
    "kind": "sequence",
    "correlate_on": ["source_ip"],
    "within_seconds": 900,
    "steps": [
        {
            "name": "failures",
            "match": {"event_types": ["failed_login"]},
            "min_count": 5,
            "window_seconds": 600,
        },
        {"name": "success", "match": {"event_types": ["successful_login"]}, "min_count": 1},
    ],
    "severity": "high",
    "points": 20,
    "cooldown_seconds": 900,
    "mitre": ["T1110", "T1078"],
}

_NEW_IP_LOGIN = {
    **_base(
        "new-ip-login",
        "Login from a never-seen IP",
        "First successful login from an IP for a user",
        ["successful_login"],
    ),
    "kind": "new_value",
    "field": "source_ip",
    "per": "username",
    "learning_days": 30,
    "min_history_events": 5,
    "severity": "medium",
    "points": 10,
    "mitre": ["T1078"],
}

_NEW_OUTBOUND = {
    **_base(
        "new-outbound-destination",
        "New outbound destination",
        "First outbound destination for a process",
        ["network_connection"],
    ),
    "kind": "new_value",
    "field": "destination_ip",
    "per": "process_name",
    "learning_days": 14,
    "min_history_events": 5,
    "severity": "low",
    "points": 5,
    "mitre": [],
    "enabled": False,
}

_SENSITIVE_SUDO = _field_match(
    "sensitive-sudo",
    "Sudo of a sensitive command",
    "Sudo execution of an administrative command",
    ["sudo_command"],
    {
        "all": [
            {
                "field": "process_name",
                "op": "in",
                "value": [
                    "visudo",
                    "passwd",
                    "useradd",
                    "usermod",
                    "userdel",
                    "chown",
                    "chmod",
                    "crontab",
                ],
            }
        ]
    },
    "high",
    20,
    ["T1548.003"],
    ["username"],
)

_NEW_USER = _field_match(
    "new-user-created",
    "New user account created",
    "A local account was created",
    ["user_created"],
    {"all": []},
    "medium",
    15,
    ["T1136.001"],
)

_PRIVILEGED_GROUP = _field_match(
    "user-added-to-privileged-group",
    "User added to a privileged group",
    "Account added to an administrative group",
    ["group_member_added"],
    {"all": [{"field": "details.group", "op": "in", "value": ["sudo", "adm", "wheel", "root"]}]},
    "high",
    25,
    ["T1098"],
    ["username"],
)

_SENSITIVE_FILE = _field_match(
    "sensitive-file-change",
    "Sensitive file changed",
    "Sensitive file changed in a security-relevant way",
    ["config_drift"],
    {
        "all": [
            {"field": "details.sensitivity", "op": "in", "value": ["high", "critical"]},
            {
                "any": [
                    {"field": "details.changed_fields", "op": "contains", "value": field}
                    for field in ("sha256", "owner", "group", "mode")
                ]
            },
        ]
    },
    "high",
    30,
    ["T1222.002"],
    ["file_path"],
)

_WORLD_WRITABLE = _field_match(
    "world-writable-sensitive-file",
    "World-writable sensitive file",
    "A sensitive file became world-writable",
    ["config_drift"],
    {"all": [{"field": "details.flags", "op": "contains", "value": "world_writable"}]},
    "critical",
    40,
    ["T1222.002"],
    ["file_path"],
)

_PERSISTENCE = _field_match(
    "persistence-change",
    "Persistence location changed",
    "A cron, systemd or other persistence location changed",
    ["config_drift"],
    {
        "all": [
            {
                "field": "details.category",
                "op": "in",
                "value": ["cron", "systemd", "authorized_keys", "ld_preload", "shell_profile"],
            }
        ]
    },
    "high",
    25,
    ["T1053.003", "T1543.002", "T1098.004"],
    ["file_path"],
)

_LISTEN_ALL = _field_match(
    "new-listening-port-all-interfaces",
    "Listening on all interfaces",
    "A new listening socket bound to all interfaces",
    ["new_listening_port"],
    {"all": [{"field": "details.bind_scope", "op": "eq", "value": "all_interfaces"}]},
    "medium",
    10,
    ["T1571"],
)

_SUSPICIOUS_PROCESS = _field_match(
    "suspicious-process",
    "Executable from a temporary location",
    "Process executable was launched from a temporary location",
    ["suspicious_process"],
    {"all": []},
    "high",
    20,
    ["T1059"],
    ["username"],
)

_RECON_TOOL = _field_match(
    "recon-or-attack-tool-installed",
    "Reconnaissance tool installed",
    "A package commonly used for reconnaissance was installed",
    ["package_installed"],
    {
        "all": [
            {
                "field": "details.package",
                "op": "in",
                "value": ["nmap", "ncat", "netcat", "hydra", "john", "sqlmap", "masscan"],
            }
        ]
    },
    "medium",
    10,
    ["T1595"],
)

DEFINITIONS: tuple[dict[str, Any], ...] = (
    _SSH_BRUTEFORCE,
    _SSH_SPRAYING,
    _SSH_DISTRIBUTED,
    _PREAUTH_SCANNING,
    _SEQUENCE_SUCCESS,
    _NEW_IP_LOGIN,
    _NEW_OUTBOUND,
    _SENSITIVE_SUDO,
    _NEW_USER,
    _PRIVILEGED_GROUP,
    _SENSITIVE_FILE,
    _WORLD_WRITABLE,
    _PERSISTENCE,
    _LISTEN_ALL,
    _SUSPICIOUS_PROCESS,
    _RECON_TOOL,
)

DEFAULT_RULES: tuple[dict[str, Any], ...] = tuple(
    {**definition, "default_definition_json": json.dumps(definition, sort_keys=True)}
    for definition in DEFINITIONS
)
