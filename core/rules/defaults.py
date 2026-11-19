"""Built-in rule definitions. Phase 5 seeds the threshold example; Phase 6 adds more."""

from __future__ import annotations

import json
from typing import Any

__all__ = ["DEFAULT_RULES"]

_SSH_BRUTEFORCE: dict[str, Any] = {
    "id": "ssh-bruteforce-by-ip",
    "name": "SSH brute force from one IP",
    "description": "Repeated failed logins from the same source IP",
    "kind": "threshold",
    "enabled": True,
    "match": {"event_types": ["failed_login", "invalid_user"], "conditions": {"all": []}},
    "scope": {"exclude_allowlisted": True},
    "actions": {"create_incident": True, "notify": True, "tags": ["brute-force"]},
    "mitre": ["T1110.001"],
    "group_by": ["source_ip"],
    "aggregate": {"type": "count"},
    "window_mode": "sliding",
    "fixed_alignment": None,
    "cooldown_seconds": 900,
    "tiers": [
        {
            "label": "Repeated failures",
            "count": 5,
            "window_seconds": 600,
            "severity": "medium",
            "points": 15,
        },
        {
            "label": "Sustained attack",
            "count": 20,
            "window_seconds": 600,
            "severity": "high",
            "points": 30,
        },
        {"label": "Burst", "count": 50, "window_seconds": 60, "severity": "critical", "points": 45},
    ],
}

DEFAULT_RULES: tuple[dict[str, Any], ...] = (
    {**_SSH_BRUTEFORCE, "default_definition_json": json.dumps(_SSH_BRUTEFORCE, sort_keys=True)},
)
