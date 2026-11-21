"""Generated test events from the *real* collector parsers and normalizer.

Unit tests must not hand-write payloads that imitate collector output: the
``source`` name, description wording and field set drifted in the past
(``auth.log`` vs ``auth_log``). These helpers build events from synthetic raw
log lines through the production parser/normalizer/severity pipeline instead.
Only the severity of the second event is pinned by callers that need a mixed
severity series; all other fields come from the real code path.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from collectors.logs import parse_auth_line
from engine.ingest import prepare_event

AUTH_LOG_LINES = (
    "2026-11-19T10:00:00+00:00 sshd[1]: Failed password for admin from 203.0.113.45 port 2200",
    "2026-11-19T10:05:00+00:00 sshd[1]: Failed password for invalid user admin "
    "from 203.0.113.46 port 2201",
    "2026-11-19T10:10:00+00:00 sshd[1]: Failed password for monitor from 198.51.100.7 port 2202",
)


def failed_login_events(
    now: datetime | None = None, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    """Three failed-login events produced by the real auth.log parser."""
    events: list[dict[str, Any]] = []
    for line in AUTH_LOG_LINES:
        raw = parse_auth_line(line)
        assert raw is not None, f"parser rejected fixture line: {line}"
        prepared = prepare_event(raw, db_path=db_path, now=now)
        assert prepared is not None
        events.append(prepared[0])
    assert all(event["source"] == "auth_log" for event in events)
    assert all(event["event_type"] == "failed_login" for event in events)
    return events
