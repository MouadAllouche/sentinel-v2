"""Deterministic demo database seed for the Playwright integration fixtures.

Writes only to the requested database path. Monitored system paths are refused,
and the default path stays inside ``demo_workdir/`` in the project. The demo
credentials are intentionally well-known and must never be used for a real
Sentinel installation.
"""

from __future__ import annotations

import argparse
import json
import os
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from storage.auth_repository import create_user, get_user_by_name
from storage.database import get_connection, init_db
from storage.incident_repository import add_note, set_incident_status
from storage.repositories import query_events, save_events
from storage.risk_repository import upsert_risk_assessment

DEFAULT_PASSWORD = "demo-password-123"  # noqa: S105 - demo-only credential, documented in DECISIONS
_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = _ROOT / "demo_workdir" / "sentinel.db"
_BLOCKED = frozenset({"etc", "shadow", "passwd"})

__all__ = ["DEFAULT_DB", "DEFAULT_PASSWORD", "seed"]


def _safe_path(db_path: str | Path) -> Path:
    resolved = Path(db_path).resolve()
    parts = {part.lower() for part in resolved.parts}
    if parts & _BLOCKED or ("var" in parts and "log" in parts):
        raise ValueError("refusing to seed a monitored system path")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _events(now: str) -> list[dict[str, Any]]:
    base = datetime.fromisoformat(now)
    rows: list[dict[str, Any]] = []
    for index in range(12):
        stamp = (base - timedelta(minutes=5 * index)).isoformat()
        ip = "203.0.113.45" if index % 3 else "198.51.100.7"
        rows.append(
            {
                "timestamp": stamp,
                "source": "auth_log",
                "event_type": "failed_login",
                "severity": "low" if index % 3 else "medium",
                "description": f"failed password for root from {ip}",
                "username": "root",
                "source_ip": ip,
                "process_name": "sshd",
                "severity_source": "default",
            }
        )
    extras = [
        ("successful_login", "medium", "auth_log", "accepted publickey for root", "203.0.113.45"),
        ("sudo_command", "high", "journald", "sudo: root executed /usr/bin/apt", "203.0.113.45"),
        (
            "network_connection",
            "low",
            "network",
            "outbound connection to 192.0.2.10:443",
            "203.0.113.45",
        ),
        ("config_drift", "high", "filesystem", "sshd_config permissions changed", "203.0.113.45"),
        ("anomaly", "medium", "baseline", "failed_login count above expected band", "198.51.100.7"),
    ]
    for index, (event_type, severity, source, description, ip) in enumerate(extras):
        rows.append(
            {
                "timestamp": (base - timedelta(minutes=index + 1)).isoformat(),
                "source": source,
                "event_type": event_type,
                "severity": severity,
                "description": description,
                "source_ip": ip,
                "username": "root",
                "severity_source": "default",
            }
        )
    return rows


def _standard_incident(path: Path, timestamp: str) -> None:
    """One deterministic incident so the investigation UI can be demoed end to end."""
    with closing(get_connection(path)) as connection:
        exists = connection.execute(
            "SELECT id FROM incidents WHERE correlation_key = ?", ("demo-standard",)
        ).fetchone()
    if exists:
        return
    event_ids = [int(item["id"]) for item in query_events({}, db_path=path)["items"][:4]]
    if not event_ids:
        return
    with closing(get_connection(path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO incidents(correlation_key, title, status, first_seen, last_seen, "
            "primary_ip, primary_username, severity, risk_score, summary, mitre_json, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "demo-standard",
                "Possible credential guessing",
                "investigating",
                timestamp,
                timestamp,
                "203.0.113.45",
                "root",
                "high",
                85,
                "Repeated failed logins followed by a successful login.",
                json.dumps(["T1110"]),
                timestamp,
                timestamp,
            ),
        )
        incident_id = int(cursor.lastrowid or 0)
        for event_id in event_ids:
            connection.execute(
                "INSERT INTO incident_events(incident_id, event_id, relation_reason, "
                "link_strength) VALUES (?, ?, ?, ?)",
                (incident_id, event_id, "Same source IP 203.0.113.45", "strong"),
            )
        connection.execute(
            "INSERT INTO rule_findings(rule_id, rule_version, group_key, tier_index, severity, "
            "points, window_start, window_end, observed, evidence_event_ids_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ssh-bruteforce-by-ip",
                1,
                "203.0.113.45",
                0,
                "high",
                45,
                timestamp,
                timestamp,
                4,
                json.dumps(event_ids),
                timestamp,
            ),
        )
    add_note(incident_id, "admin", "Reviewing the repeated failures.", path)
    set_incident_status(incident_id, "open", "investigating", "admin", "Initial triage", path)
    upsert_risk_assessment(
        "incident",
        incident_id,
        {
            "score": 85,
            "severity": "high",
            "computed_at": timestamp,
            "reasons": [
                {
                    "kind": "rule",
                    "rule_id": "ssh-bruteforce-by-ip",
                    "tier_label": "High",
                    "points": 45,
                    "severity": "high",
                    "explanation": "Repeated failed logins from one IP.",
                    "evidence_event_ids": event_ids,
                },
                {
                    "kind": "summary",
                    "points": 0,
                    "raw_score": 85,
                    "score": 85,
                    "capped": False,
                    "severity": "high",
                    "severity_basis": "score band",
                    "explanation": "Severity high from score band",
                },
            ],
        },
        path,
    )


def seed(
    db_path: str | Path = DEFAULT_DB,
    password: str = DEFAULT_PASSWORD,
    now: str | None = None,
) -> dict[str, int]:
    """Seed users and events; repeated calls do not duplicate either."""
    if len(password) < 12:
        raise ValueError("demo password must be at least 12 characters")
    path = _safe_path(db_path)
    timestamp = now or datetime.now(UTC).isoformat()
    init_db(path)
    for username, role in (("admin", "admin"), ("viewer", "viewer")):
        if get_user_by_name(username, path) is None:
            create_user(username, password, role, path)
    events = _events(timestamp)
    save_events(events, path)
    _standard_incident(path, timestamp)
    return {"events": len(events), "users": 2, "incidents": 1}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a Sentinel demo database")
    parser.add_argument(
        "--db", default=str(DEFAULT_DB), help="database path (default: demo_workdir/)"
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("SENTINEL_DEMO_PASSWORD", DEFAULT_PASSWORD),
        help="demo password (min 12 characters)",
    )
    args = parser.parse_args()
    result = seed(args.db, args.password)
    print(f"seeded {result['events']} events and {result['users']} users into {args.db}")
    print("demo accounts: admin / viewer with the supplied password (demo use only)")


if __name__ == "__main__":
    main()
