"""dpkg.log collection, incremental and read-only."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from collectors import CollectionResult
from collectors.logs import read_incremental_lines
from core.timeutil import to_utc_iso

_DPKG_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (install|remove|purge) (\S+)(?: (\S+))?"
)


def parse_dpkg_line(line: str) -> dict[str, Any] | None:
    """Parse one dpkg log line, or return None for unrelated text."""
    if not isinstance(line, str) or len(line) > 4096:
        return None
    try:
        match = _DPKG_LINE.match(line.strip())
        if not match:
            return None
        stamp, action, package, version = match.groups()
        installed = action == "install"
        return {
            "timestamp": to_utc_iso(stamp),
            "source": "dpkg",
            "event_type": "package_installed" if installed else "package_removed",
            "severity": "low",
            "description": f"Package {package} {'installed' if installed else 'removed'}",
            "details": {"package": package, "version": version or ""},
        }
    except (ValueError, OverflowError):
        return None


def collect_dpkg_events(
    path: str | Path, state: dict[str, Any] | None, now: Any = None
) -> CollectionResult:
    """Collect new dpkg events; ``now`` is accepted for API symmetry."""
    del now  # dpkg lines carry their own timestamps.
    lines, warnings, new_state = read_incremental_lines(path, state)
    events = []
    for line in lines:
        event = parse_dpkg_line(line)
        if event is not None:
            events.append(event)
    return CollectionResult(events=events, warnings=warnings, state=new_state)
