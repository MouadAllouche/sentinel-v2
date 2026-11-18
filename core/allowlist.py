"""Pure allowlist matching. Suppressed evidence is annotated, never dropped."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.events import SEVERITY_ORDER, VALID_SEVERITIES
from core.timeutil import parse_ts

__all__ = ["Entry", "matches", "reduce_severity", "validate_entry"]

KINDS = frozenset({"ip", "cidr", "username", "command", "event_type", "path"})
SCOPES = frozenset({"annotate", "suppress_alerts", "lower_severity"})


@dataclass(frozen=True)
class Entry:
    id: int | str
    kind: str
    value: str
    scope: str
    reason: str
    expires_at: str | None = None
    enabled: bool = True


def validate_entry(obj: dict[str, Any] | Entry) -> Entry:
    """Validate an allowlist entry; a meaningful reason is mandatory."""
    if isinstance(obj, Entry):
        data: dict[str, Any] = {
            "id": obj.id,
            "kind": obj.kind,
            "value": obj.value,
            "scope": obj.scope,
            "reason": obj.reason,
            "expires_at": obj.expires_at,
            "enabled": obj.enabled,
        }
    else:
        data = dict(obj)
    reason = data.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < 5:
        raise ValueError("allowlist reason must be at least 5 characters")
    if data.get("kind") not in KINDS:
        raise ValueError(f"invalid allowlist kind: {data.get('kind')!r}")
    if data.get("scope") not in SCOPES:
        raise ValueError(f"invalid allowlist scope: {data.get('scope')!r}")
    if not isinstance(data.get("value"), str) or not data["value"].strip():
        raise ValueError("allowlist value must be a non-empty string")
    expires = data.get("expires_at")
    if expires is not None:
        parse_ts(str(expires))
    if "id" not in data:
        raise ValueError("allowlist entry requires an id")
    return Entry(
        id=data["id"],
        kind=data["kind"],
        value=data["value"],
        scope=data["scope"],
        reason=reason.strip(),
        expires_at=expires,
        enabled=bool(data.get("enabled", True)),
    )


def _is_expired(entry: Entry, now: datetime) -> bool:
    if entry.expires_at is None:
        return False
    return parse_ts(entry.expires_at) <= now


def _matches_one(entry: Entry, event: dict[str, Any]) -> bool:
    value = entry.value
    if entry.kind == "ip":
        # master 4.1: source_ip is the remote initiator; use cidr for outbound ranges.
        return event.get("source_ip") == value
    if entry.kind == "cidr":
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError:
            return False
        for address in (event.get("source_ip"), event.get("destination_ip")):
            if not address:
                continue
            try:
                if ipaddress.ip_address(str(address)) in network:
                    return True
            except ValueError:
                continue
        return False
    if entry.kind == "username":
        return event.get("username") == value
    if entry.kind == "event_type":
        return event.get("event_type") == value
    if entry.kind == "path":
        return event.get("file_path") == value
    if entry.kind == "command":
        executable = str((event.get("details") or {}).get("command_executable", ""))
        return event.get("process_name") == value or os.path.basename(executable) == value
    return False


def matches(
    event: dict[str, Any], entries: list[Entry] | tuple[Entry, ...], now: datetime
) -> list[Entry]:
    """Return enabled, unexpired entries that apply to ``event``."""
    return [
        entry
        for entry in entries
        if entry.enabled and not _is_expired(entry, now) and _matches_one(entry, event)
    ]


def reduce_severity(severity: str) -> str:
    """Lower a severity by one level, with a floor of ``low``."""
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"invalid severity: {severity!r}")
    lowered = max(0, SEVERITY_ORDER[severity] - 1)
    return next(name for name, rank in SEVERITY_ORDER.items() if rank == lowered)
