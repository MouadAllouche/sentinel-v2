"""Hourly host-level system information (read-only)."""

from __future__ import annotations

import platform
import socket
from datetime import UTC, datetime
from typing import Any

import psutil

from core.timeutil import utc_now


def collect_system_info(now: datetime | None = None) -> dict[str, Any]:
    """Return one provisional ``system_info`` event."""
    reference = now or utc_now()
    boot_time = psutil.boot_time()
    return {
        "timestamp": reference.isoformat(),
        "source": "system",
        "event_type": "system_info",
        "severity": "low",
        "description": "Host system information collected",
        "details": {
            "hostname": socket.gethostname(),
            "kernel": platform.release(),
            "boot_time": datetime.fromtimestamp(boot_time, tz=UTC).isoformat(),
            "uptime_seconds": max(0, int(reference.timestamp() - boot_time)),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent,
            "logged_in_users": len(psutil.users()),
        },
    }
