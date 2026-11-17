"""journald collection via an argument-list ``journalctl`` invocation.

No shell is ever used. Missing binaries, timeouts and malformed JSON degrade to
warnings so one unavailable source never stops the collection cycle.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any

from collectors import CollectionResult
from collectors.logs import extract_timestamp, parse_auth_line
from core.timeutil import to_utc_iso, utc_now

TIMEOUT_SECONDS = 20


def _since_from_state(state: dict[str, Any] | None, now: datetime | None) -> str:
    if state and state.get("since"):
        return str(state["since"])
    reference = now or utc_now()
    return (reference - timedelta(hours=1)).isoformat()


def collect_journald_events(
    unit: str, state: dict[str, Any] | None, now: datetime | None = None
) -> CollectionResult:
    """Collect auth events from ``journalctl`` JSON output."""
    arguments = [
        "journalctl",
        "--since",
        _since_from_state(state, now),
        "--output=json",
        "-u",
        unit,
        "--no-pager",
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            arguments,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CollectionResult(warnings=[f"journalctl: {type(exc).__name__}"])

    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    cursor = state.get("cursor") if state else None
    since = state.get("since") if state else None
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            warnings.append("journald: malformed JSON line skipped")
            continue
        message = entry.get("MESSAGE")
        if not isinstance(message, str):
            continue
        try:
            iso = extract_timestamp(message, now=now)
            parsed_line = message
        except ValueError:
            try:
                microseconds = int(entry.get("__REALTIME_TIMESTAMP", 0))
                timestamp = datetime.fromtimestamp(microseconds / 1_000_000, tz=UTC)
                iso = to_utc_iso(timestamp)
            except (ValueError, TypeError, OverflowError, OSError):
                warnings.append("journald: invalid timestamp line skipped")
                continue
            parsed_line = f"{iso} host {message}"
        event = parse_auth_line(parsed_line, now=now)
        if event is not None:
            events.append(event)
            cursor = entry.get("__CURSOR", cursor)
            since = iso
    new_state = {"cursor": cursor, "since": since} if events else state
    return CollectionResult(events=events, warnings=warnings, state=new_state)
