"""Listening-port collection; the first run seeds state silently."""

from __future__ import annotations

import ipaddress
import json
from datetime import datetime
from typing import Any

import psutil

from collectors import CollectionResult
from collectors.network import get_process_details
from core.timeutil import utc_now

_ALL_INTERFACES = {"0.0.0.0", "::"}  # noqa: S104 - classification constants, not a bind call
MAX_TRACKED = 5_000


def classify_bind_scope(address: str) -> str:
    """Classify a bind address without any DNS or GeoIP lookup."""
    if address in _ALL_INTERFACES:
        return "all_interfaces"
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return "public"
    if parsed.is_loopback:
        return "loopback"
    if parsed.is_private:
        return "private"
    return "public"


def _protocol(connection: Any) -> str:
    kind = str(getattr(connection, "type", ""))
    if "STREAM" in kind:
        return "tcp"
    if "DGRAM" in kind:
        return "udp"
    return kind


def _port_key(connection: Any) -> tuple[str, str, int, int | None]:
    local = getattr(connection, "laddr", None)
    return (
        _protocol(connection),
        str(getattr(local, "ip", "")),
        int(getattr(local, "port", 0)),
        getattr(connection, "pid", None),
    )


def collect_listening_events(
    state: dict[str, Any] | None, now: datetime | None = None
) -> CollectionResult:
    """Emit new listening ports after the initial seeding run."""
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError, psutil.Error) as exc:
        return CollectionResult(warnings=[f"listening: {type(exc).__name__}"])

    seen = set((state or {}).get("seen", []))
    seeded = bool((state or {}).get("seeded"))
    reference = (now or utc_now()).isoformat()
    events: list[dict[str, Any]] = []
    for connection in connections:
        if getattr(connection, "status", None) != psutil.CONN_LISTEN:
            continue
        key = _port_key(connection)
        serialised = json.dumps(key, separators=(",", ":"))
        if serialised in seen:
            continue
        seen.add(serialised)
        if not seeded:
            continue
        name, _username = get_process_details(key[3])
        events.append(
            {
                "timestamp": reference,
                "source": "listening",
                "event_type": "new_listening_port",
                "severity": "low",
                "description": f"New listening port {key[2]} detected",
                "process_id": key[3],
                "process_name": name,
                "details": {
                    "protocol": key[0],
                    "bind_address": key[1],
                    "port": key[2],
                    "bind_scope": classify_bind_scope(key[1]),
                },
            }
        )
    warnings: list[str] = []
    if len(seen) > MAX_TRACKED:
        warnings.append(f"listening: state capped at {MAX_TRACKED} ports")
        seen = set(list(seen)[-MAX_TRACKED:])
    return CollectionResult(
        events=events, warnings=warnings, state={"seeded": True, "seen": list(seen)}
    )
