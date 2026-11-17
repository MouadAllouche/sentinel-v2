"""Process collection from psutil snapshots; never reads command lines."""

# ruff: noqa: S108 - these literal paths are suspicious-location markers, never opened.
from __future__ import annotations

from datetime import datetime
from typing import Any

import psutil

from collectors import CollectionResult
from core.timeutil import utc_now

_SUSPICIOUS_PREFIXES = ("/tmp/", "/var/tmp/", "/dev/shm/", "/run/user/")
MAX_TRACKED = 5_000


def is_suspicious_exe(exe: str | None) -> bool:
    """Flag executables from temporary/user locations or deleted images."""
    if not exe:
        return False
    if exe == "(deleted)":
        return True
    for prefix in _SUSPICIOUS_PREFIXES:
        if exe.startswith(prefix):
            return not (prefix == "/run/user/" and "systemd" in exe)
    return False


def collect_process_events(
    state: dict[str, Any] | None,
    now: datetime | None = None,
    *,
    max_events: int = 200,
) -> CollectionResult:
    """Emit suspicious processes on the seeding run, then new processes only."""
    try:
        processes = list(
            psutil.process_iter(["pid", "ppid", "name", "username", "exe", "create_time"])
        )
    except (psutil.Error, OSError) as exc:
        return CollectionResult(warnings=[f"processes: {type(exc).__name__}"])

    current: list[tuple[Any, Any]] = []
    for process in processes:
        try:
            info = process.info
            current.append((info.get("pid"), info.get("create_time")))
        except (psutil.Error, AttributeError, TypeError):
            continue

    previous = {(item[0], item[1]) for item in (state or {}).get("seen", [])}
    seeded = bool((state or {}).get("seeded"))
    reference = (now or utc_now()).isoformat()
    events: list[dict[str, Any]] = []
    warnings: list[str] = []

    for process in processes:
        try:
            info = process.info
        except (psutil.Error, AttributeError):
            continue
        key = (info.get("pid"), info.get("create_time"))
        suspicious = is_suspicious_exe(info.get("exe"))
        if (not seeded or key not in previous) and suspicious and len(events) < max_events:
            events.append(
                {
                    "timestamp": reference,
                    "source": "process",
                    "event_type": "suspicious_process",
                    "severity": "low",
                    "description": f"Suspicious executable for process {info.get('pid')}",
                    "process_id": info.get("pid"),
                    "process_name": info.get("name"),
                    "username": info.get("username"),
                    "details": {"ppid": info.get("ppid")},
                }
            )
        elif seeded and key not in previous and len(events) < max_events:
            events.append(
                {
                    "timestamp": reference,
                    "source": "process",
                    "event_type": "process_started",
                    "severity": "low",
                    "description": f"Process {info.get('name')} started",
                    "process_id": info.get("pid"),
                    "process_name": info.get("name"),
                    "username": info.get("username"),
                    "details": {"ppid": info.get("ppid")},
                }
            )

    new_count = sum((key not in previous) & seeded for key in current)
    if new_count > len(events) or (not seeded and len(events) == max_events):
        warnings.append(f"processes: capped at {max_events} events on this run")
    if len(current) > MAX_TRACKED:
        warnings.append(f"processes: state capped at {MAX_TRACKED} entries")
        current = current[-MAX_TRACKED:]
    return CollectionResult(
        events=events,
        warnings=warnings,
        state={"seeded": True, "seen": [list(item) for item in current]},
    )
