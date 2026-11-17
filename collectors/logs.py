"""auth.log (rsyslog) collection.

All log text is untrusted: bounded patterns, a line-length cap, replacement
decoding, and per-line error handling. No line is ever interpolated into SQL,
a path or a command.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from collectors import CollectionResult
from core.timeutil import to_utc_iso

MAX_LINE_BYTES = 4096

FAILED_LOGIN = r"Failed password for (?:invalid user )?(\S+) from (\S+)"
SUCCESSFUL_LOGIN = r"Accepted (?:password|publickey|keyboard-interactive/pam) for (\S+) from (\S+)"
INVALID_USER = r"Invalid user (\S+) from (\S+)"
PREAUTH_DISCONNECT = (
    r"Connection closed by (?:authenticating|invalid) user (\S+) (\S+) port \d+ \[preauth\]"
)
SUDO_COMMAND = r"sudo:\s+(\S+)\s+:.*?USER=(\S+)\s*;\s*COMMAND=(.+)$"
SU_COMMAND = r"su(?:\[\d+\])?:\s+\(to (\S+)\) (\S+) on"
USER_CREATED = r"new user: name=(\S+),"
USER_DELETED = r"delete user '(\S+)'"
GROUP_MEMBER_ADD = r"add '(\S+)' to (?:shadow )?group '(\S+)'"
PASSWORD_CHANGED = r"password changed for (\S+)"  # noqa: S105 - regex name, not a secret

_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        FAILED_LOGIN,
        SUCCESSFUL_LOGIN,
        INVALID_USER,
        PREAUTH_DISCONNECT,
        SUDO_COMMAND,
        SU_COMMAND,
        USER_CREATED,
        USER_DELETED,
        GROUP_MEMBER_ADD,
        PASSWORD_CHANGED,
    )
)
_ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")
_SYSLOG_PREFIX = re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})")


def state_key(path: str | Path) -> str:
    """Return the collector_state key for an auth.log path."""
    return f"auth_log:{path}"


def extract_timestamp(line: str, year: int | None = None, now: Any = None) -> str:
    """Extract an ISO or syslog timestamp prefix and return UTC ISO text."""
    text = line.strip()
    match = _ISO_PREFIX.match(text)
    if match:
        return to_utc_iso(match.group(0), year=year, now=now)
    match = _SYSLOG_PREFIX.match(text)
    if match:
        month, day, clock = match.groups()
        return to_utc_iso(f"{month} {int(day):02d} {clock}", year=year, now=now)
    raise ValueError("line has no recognised timestamp prefix")


def _base_event(line: str, year: int | None, now: Any) -> dict[str, Any]:
    return {
        "timestamp": extract_timestamp(line, year=year, now=now),
        "source": "auth_log",
        "severity": "low",
    }


def parse_auth_line(line: str, year: int | None = None, now: Any = None) -> dict[str, Any] | None:
    """Parse one auth.log line into a provisional event, or None if unmatched."""
    if not isinstance(line, str) or len(line) > MAX_LINE_BYTES:
        return None
    try:
        base = _base_event(line, year, now)
        for pattern in _PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            groups = match.groups()
            if pattern.pattern == FAILED_LOGIN:
                return {
                    **base,
                    "event_type": "failed_login",
                    "description": f"Failed SSH login attempt for {groups[0]}",
                    "username": groups[0],
                    "source_ip": groups[1],
                }
            if pattern.pattern == SUCCESSFUL_LOGIN:
                return {
                    **base,
                    "event_type": "successful_login",
                    "description": f"Successful SSH login for {groups[0]}",
                    "username": groups[0],
                    "source_ip": groups[1],
                }
            if pattern.pattern == INVALID_USER:
                return {
                    **base,
                    "event_type": "invalid_user",
                    "description": f"Invalid user {groups[0]} login attempt",
                    "username": groups[0],
                    "source_ip": groups[1],
                }
            if pattern.pattern == PREAUTH_DISCONNECT:
                return {
                    **base,
                    "event_type": "preauth_disconnect",
                    "description": f"Pre-authentication disconnect for {groups[0]}",
                    "username": groups[0],
                    "source_ip": groups[1],
                }
            if pattern.pattern == SUDO_COMMAND:
                command = groups[2].split()
                executable = command[0] if command else ""
                return {
                    **base,
                    "event_type": "sudo_command",
                    "description": f"User {groups[0]} executed a sudo command as {groups[1]}",
                    "username": groups[0],
                    "process_name": os.path.basename(executable),
                    "details": {
                        "target_user": groups[1],
                        "command_executable": executable,
                        "command_args_count": max(0, len(command) - 1),
                    },
                }
            if pattern.pattern == SU_COMMAND:
                return {
                    **base,
                    "event_type": "su_command",
                    "description": f"User {groups[1]} switched to {groups[0]}",
                    "username": groups[1],
                    "details": {"target_user": groups[0]},
                }
            if pattern.pattern == USER_CREATED:
                return {
                    **base,
                    "event_type": "user_created",
                    "description": f"User account {groups[0]} created",
                    "details": {"account": groups[0]},
                }
            if pattern.pattern == USER_DELETED:
                return {
                    **base,
                    "event_type": "user_deleted",
                    "description": f"User account {groups[0]} deleted",
                    "details": {"account": groups[0]},
                }
            if pattern.pattern == GROUP_MEMBER_ADD:
                return {
                    **base,
                    "event_type": "group_member_added",
                    "description": f"User {groups[0]} added to group {groups[1]}",
                    "details": {"account": groups[0], "group": groups[1]},
                }
            if pattern.pattern == PASSWORD_CHANGED:
                return {
                    **base,
                    "event_type": "password_changed",
                    "description": f"Password changed for {groups[0]}",
                    "details": {"account": groups[0]},
                }
        return None
    except (ValueError, OverflowError):
        return None


def read_incremental_lines(
    path: str | Path, state: dict[str, Any] | None
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    """Read only complete new lines; reset on rotation or truncation."""
    warnings: list[str] = []
    try:
        with open(path, "rb") as handle:
            stats = os.fstat(handle.fileno())
            inode = stats.st_ino
            offset = state.get("offset", 0) if state and state.get("inode") == inode else 0
            if stats.st_size < offset:
                offset = 0
            handle.seek(offset)
            lines: list[str] = []
            while True:
                raw = handle.readline()
                if not raw or not raw.endswith(b"\n"):
                    break
                if len(raw.rstrip(b"\n")) > MAX_LINE_BYTES:
                    warnings.append(f"{path}: line longer than {MAX_LINE_BYTES} bytes skipped")
                else:
                    lines.append(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
                offset = handle.tell()
            return lines, warnings, {"inode": inode, "offset": offset}
    except (OSError, PermissionError) as exc:
        warnings.append(f"{path}: {type(exc).__name__}")
        return [], warnings, None


def collect_auth_events(
    path: str | Path,
    state: dict[str, Any] | None,
    now: Any = None,
    year: int | None = None,
) -> CollectionResult:
    """Collect new auth.log events without ever writing to the log file."""
    lines, warnings, new_state = read_incremental_lines(path, state)
    events = []
    for line in lines:
        event = parse_auth_line(line, year=year, now=now)
        if event is not None:
            events.append(event)
    return CollectionResult(events=events, warnings=warnings, state=new_state)
