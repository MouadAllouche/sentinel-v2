"""Network connection collection from psutil snapshots (read-only)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import psutil

from collectors import CollectionResult
from core.timeutil import utc_now

MAX_TRACKED = 20_000
EXPIRY_HOURS = 24


def get_process_details(pid: int | None) -> tuple[str | None, str | None]:
    """Return ``(name, username)`` or ``(None, None)`` on any expected failure."""
    if pid is None:
        return None, None
    try:
        process = psutil.Process(pid)
        return process.name(), process.username()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, psutil.Error):
        return None, None


def _connection_key(connection: Any) -> tuple[str, int, str, int, int | None] | None:
    local = getattr(connection, "laddr", None)
    remote = getattr(connection, "raddr", None)
    if local is None or remote is None:
        return None
    if getattr(connection, "status", None) == psutil.CONN_LISTEN:
        return None
    pid = getattr(connection, "pid", None)
    return (
        str(getattr(local, "ip", "")),
        int(getattr(local, "port", 0)),
        str(getattr(remote, "ip", "")),
        int(getattr(remote, "port", 0)),
        pid,
    )


def _serialise_key(key: tuple[str, int, str, int, int | None]) -> str:
    return json.dumps(key, separators=(",", ":"))


def collect_network_events(
    state: dict[str, Any] | None, now: datetime | None = None
) -> CollectionResult:
    """Emit an event only for connection tuples not already tracked."""
    reference = now or utc_now()
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError, psutil.Error) as exc:
        return CollectionResult(warnings=[f"network: {type(exc).__name__}"])

    seen: dict[str, str] = dict((state or {}).get("seen", {}))
    cutoff = (reference - timedelta(hours=EXPIRY_HOURS)).isoformat()
    for seen_key, last_seen in list(seen.items()):
        if last_seen < cutoff:
            del seen[seen_key]

    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    for connection in connections:
        connection_key = _connection_key(connection)
        if connection_key is None:
            continue
        serialised = _serialise_key(connection_key)
        if serialised in seen:
            seen[serialised] = reference.isoformat()
            continue
        name, username = get_process_details(getattr(connection, "pid", None))
        events.append(
            {
                "timestamp": reference.isoformat(),
                "source": "network",
                "event_type": "network_connection",
                "severity": "low",
                "description": "Network connection detected",
                "local_ip": connection_key[0],
                "destination_ip": connection_key[2],
                "destination_port": connection_key[3],
                "connection_status": getattr(connection, "status", ""),
                "process_id": connection_key[4],
                "process_name": name,
                "username": username,
            }
        )
        seen[serialised] = reference.isoformat()

    if len(seen) > MAX_TRACKED:
        overflow = len(seen) - MAX_TRACKED
        oldest = sorted(seen, key=lambda item: seen[item])[:overflow]
        for key in oldest:
            del seen[key]
        warnings.append(f"network: state capped at {MAX_TRACKED} tuples")
    return CollectionResult(events=events, warnings=warnings, state={"seen": seen})
