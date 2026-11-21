"""Reproducible, sandboxed demonstration for Sentinel.

Everything is created inside the requested workdir (``demo_workdir/`` by default).
No real system file is read or modified, no sudo is used, and no outbound network
call is made. The demo password is random, printed once and written to a
mode-0600 credentials file for the Playwright harness.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.config import load_settings
from engine.ingest import prepare_event
from engine.runner import run_once
from storage.auth_repository import create_user, get_user_by_name
from storage.database import init_db
from storage.drift_repository import add_monitored_path, list_monitored_paths, save_snapshot
from storage.incident_repository import list_incidents
from storage.repositories import count_events, get_setting, query_events, save_events, set_setting
from storage.risk_repository import get_assessment
from storage.rules_repository import seed_rules
from storage.severity_repository import seed_defaults

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKDIR = ROOT / "demo_workdir"
_BLOCKED = frozenset({"etc", "shadow", "passwd", "var"})
DEMO_PASSWORD_LENGTH = 18


def _safe_workdir(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    if _BLOCKED.intersection(part.lower() for part in resolved.parts):
        raise ValueError("refusing to create a demo inside a monitored system path")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _session_key(target: Path) -> str:
    """Create (or reuse) a private demo session key at mode 0600 in the workdir."""
    path = target / "session.key"
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            os.chmod(path, 0o600)
            return existing
    key = secrets.token_urlsafe(48)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(key + "\n")
    os.chmod(path, 0o600)
    return key


def _fake_key_line(label: str, seed: str) -> str:
    """A syntactically valid *fake* public key line (base64 blob, never key material).

    The collector stores only a SHA-256 fingerprint of the blob, so the demo can
    demonstrate key-added drift without ever persisting key material.
    """
    blob = base64.b64encode(f"ssh-ed25519-demo-{seed}".encode()).decode("ascii")
    return f"ssh-ed25519 {blob} {label}\n"


def _auth_lines(now: datetime) -> list[str]:
    """Seven benign days of history, then a spike in the last completed hour.

    The spike is deliberately placed in the last *completed* hour because the
    baseline cycle only evaluates that hour; this makes the demo's anomaly come
    from the real baseline pipeline rather than a hand-written event.
    """
    lines: list[str] = []
    for day in range(7):
        for index in range(3):
            stamp = now - timedelta(days=7 - day, hours=index * 3, minutes=index * 5)
            user = "alice" if index % 2 else "bob"
            lines.append(
                f"{stamp.isoformat()} sshd[1]: Accepted password for {user} "
                "from 198.51.100.7 port 22"
            )
            lines.append(f"{stamp.isoformat()} sudo:   {user} : USER=root ; COMMAND=/usr/bin/id")
            # A little benign failed-login noise keeps the learned mean realistic.
            failed = stamp + timedelta(minutes=2)
            lines.append(
                f"{failed.isoformat()} sshd[1]: Failed password for {user} "
                "from 198.51.100.7 port 2200"
            )

    hour_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    # Two early probes make the attack cluster the incident's earliest anchor,
    # while staying inside the rules engine's recent-event lookback.
    for index in range(2):
        stamp = hour_start + timedelta(minutes=38 + index)
        lines.append(
            f"{stamp.isoformat()} sshd[1]: Failed password for admin from 203.0.113.45 "
            f"port {2100 + index}"
        )
    # 36 failed logins inside ~6 minutes: well above the seeded z/min_absolute
    # tiers, and close enough to the anomaly to stay in the same incident.
    for index in range(36):
        stamp = hour_start + timedelta(minutes=40, seconds=index * 10)
        user = "invalid user admin" if index % 2 else "admin"
        lines.append(
            f"{stamp.isoformat()} sshd[1]: Failed password for {user} "
            f"from 203.0.113.45 port {2200 + index}"
        )
    follow_up = hour_start + timedelta(minutes=50)
    lines.append(
        f"{follow_up.isoformat()} sshd[1]: Accepted password for admin from 203.0.113.45 port 4000"
    )
    lines.append(f"{follow_up.isoformat()} sudo:   admin : USER=root ; COMMAND=/usr/sbin/visudo")

    # Benign noise from a trusted IP (allowlisted in the demo settings).
    for index in range(4):
        trusted = now - timedelta(minutes=4, seconds=index * 10)
        lines.append(
            f"{trusted.isoformat()} sshd[1]: Failed password for monitor from 192.0.2.10 port 5000"
        )
    return sorted(lines)


def _files(workdir: Path, now: datetime) -> dict[str, Path]:
    etc = workdir / "etc"
    (etc / "sudoers.d").mkdir(parents=True, exist_ok=True)
    (etc / "cron.d").mkdir(parents=True, exist_ok=True)
    sshd = etc / "sshd_config"
    sshd.write_text("# sentinel demo configuration\nPermitRootLogin no\n", encoding="utf-8")
    sudoers = "demo ALL=(ALL) NOPASSWD: /usr/bin/id\n"
    (etc / "sudoers.d" / "demo").write_text(sudoers, encoding="utf-8")
    (etc / "authorized_keys").write_text(
        _fake_key_line("sentinel-demo", "baseline"), encoding="utf-8"
    )
    auth_log = workdir / "auth.log"
    auth_log.write_text("\n".join(_auth_lines(now)) + "\n", encoding="utf-8")
    return {
        "auth_log": auth_log,
        "sshd": sshd,
        "authorized_keys": etc / "authorized_keys",
        "cron": etc / "cron.d" / "backup",
    }


def _settings(workdir: Path, db: Path, auth_log: Path) -> Path:
    target = workdir / "settings.toml"
    target.write_text(
        f"[paths]\n"
        f'database = "{db}"\n'
        f'auth_log = "{auth_log}"\n'
        f'dpkg_log = "{workdir / "dpkg.log"}"\n'
        f'log_dir = "{workdir / "logs"}"\n'
        f"\n[collectors]\n"
        f'auth_source = "auth_log"\n'
        f"network = false\nlistening = false\nprocesses = false\n"
        f"filesystem = false\ndpkg = false\nsystem = false\n"
        f"\n[notifications]\nenabled = true\n"
        f"\n[drift]\nallow_custom_paths = true\n",
        encoding="utf-8",
    )
    return target


def _monitor_paths(db: Path, files: dict[str, Path], now: datetime) -> None:
    specs = [
        (files["sshd"], "file", "ssh", "high"),
        (files["authorized_keys"], "authorized_keys", "authorized_keys", "critical"),
        (files["cron"].parent, "dir", "cron", "high"),
    ]
    for path, kind, category, sensitivity in specs:
        add_monitored_path(
            {
                "path": str(path),
                "kind": kind,
                "category": category,
                "sensitivity": sensitivity,
                "enabled": True,
            },
            "demo",
            db,
            allow_custom_paths=True,
        )
        from collectors.filesystem import take_snapshot

        spec = next(item.as_spec() for item in list_monitored_paths(db) if item.path == str(path))
        snapshot, warnings = take_snapshot(spec, now=now)
        save_snapshot(snapshot, is_baseline=True, db_path=db)
        if warnings:
            print("demo baseline warnings:", "; ".join(warnings))


def _synthetic_events(db: Path, now: datetime) -> None:
    raw_events = [
        {
            "timestamp": (now - timedelta(minutes=2)).isoformat(),
            "source": "network",
            "event_type": "network_connection",
            "severity": "low",
            "description": "outbound 192.0.2.10:443",
            "source_ip": "203.0.113.45",
            "destination_ip": "192.0.2.10",
            "destination_port": 443,
        },
        {
            "timestamp": (now - timedelta(minutes=1)).isoformat(),
            "source": "dpkg",
            "event_type": "package_installed",
            "severity": "low",
            "description": "install nmap",
            "process_name": "apt",
        },
    ]
    prepared = [prepare_event(item, db, now=now) for item in raw_events]
    save_events([item[0] for item in prepared if item], db)


def _print_demo_details(
    target: Path,
    incidents: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    assessment: dict[str, Any] | None,
    db: Path,
    now: datetime,
) -> None:
    """Print the explained highlights the demo exists to showcase (spec 18.1 step 4)."""
    from core.normalizer import compute_event_hash
    from core.timeline import build_timeline, component_with_links, explain_incident
    from storage.incident_repository import get_incident
    from storage.notification_repository import list_notifications
    from storage.repositories import get_events_by_ids
    from storage.rules_repository import list_findings

    print("Incidents:")
    for incident in incidents:
        score = get_assessment("incident", incident["id"], db)
        print(
            f"  #{incident['id']} {incident['title']} — "
            f"{(score or {}).get('severity', 'low')} / {(score or {}).get('score', 0)}"
        )

    if incidents:
        stored = get_incident(incidents[0]["id"], db_path=db)
        if stored:
            events = list(get_events_by_ids(stored.get("event_ids", []), db).values())
            for event in events:
                event.setdefault("event_hash", compute_event_hash(event))
            component = component_with_links(events, now)
            rule_findings = list_findings({}, db_path=db, limit=500)
            timeline = build_timeline(component, events, component.links, rule_findings)
            print("Timeline excerpt:")
            for entry in timeline[:5]:
                print(f"  {entry['timestamp']} [{entry['kind']}] {entry['summary'][:90]}")
            explanation = explain_incident(component, events, rule_findings)
            print("Grouping reasons:")
            # Correlation emits one reason per event pair; collapse identical
            # reasons so the demo stays readable without dropping any of them.
            for strength in ("strong", "weak"):
                for reason, count in sorted(Counter(explanation["grouping"][strength]).items()):
                    suffix = f" (×{count})" if count > 1 else ""
                    print(f"  {strength}: {reason}{suffix}")

    print("Rule findings by tier:")
    severities: dict[str, int] = {}
    for item in findings:
        severities[item.get("severity", "low")] = severities.get(item.get("severity", "low"), 0) + 1
    for severity, count in sorted(severities.items()):
        print(f"  {severity}: {count}")

    anomalies = query_events({"event_type": ["anomaly"]}, db_path=db)["items"]
    for item in anomalies[:3]:
        print(f"Anomaly: {item.get('description', '')}")

    drift = query_events({"event_type": ["config_drift"]}, db_path=db)["items"]
    for item in drift[:3]:
        print(f"Drift: {item.get('description', '')}")

    log = list_notifications(db_path=db)
    sink = target / "logs" / "notifications.jsonl"
    print(f"Notifications: {len(log)} logged; local file sink at {sink}")


def _demo_live(target: Path) -> None:  # pragma: no cover - interactive demonstration only
    """Append one synthetic event per prompt until interrupted, then re-analyse."""
    from core.timeutil import utc_now

    print("Live demo: press Enter to append a failed login, or type 'q' to stop.")
    while True:
        try:
            answer = input("> ").strip()
        except EOFError:
            break
        if answer.lower() in {"q", "quit", "exit"}:
            break
        append_demo_event(target, utc_now())
        print(
            "Appended one synthetic event. Run 'python cli.py analyze --db <demo.db>' to refresh."
        )


def append_demo_event(target: Path, now: datetime) -> None:
    """Append one synthetic auth.log line to a running demo sandbox."""
    from engine.ingest import run_collection

    line = (
        f"{now.isoformat()} sshd[1]: Failed password for invalid user admin "
        f"from 203.0.113.45 port {4000 + now.second}\n"
    )
    with (target / "auth.log").open("a", encoding="utf-8") as handle:
        handle.write(line)
    settings = load_settings(config_path=target / "settings.toml")
    run_collection(settings, target / "demo.db", now=now)


def build_demo(
    workdir: str | Path = DEFAULT_WORKDIR,
    *,
    now: datetime | None = None,
    reset: bool = False,
    print_password: bool = True,
    live: bool = False,
) -> dict[str, Any]:
    """Create (or refresh) a complete demo sandbox; repeated calls are idempotent."""
    target = _safe_workdir(workdir)
    if reset:
        for item in target.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    reference = (now or datetime.now(UTC)).replace(microsecond=0)
    db = target / "demo.db"
    init_db(db)
    seed_defaults(db)
    seed_rules(db)
    settings_path = _settings(target, db, target / "auth.log")
    settings = load_settings(config_path=settings_path)

    _session_key(target)
    credentials = target / "credentials.json"
    if get_user_by_name("demo-admin", db) is not None and credentials.exists():
        # Re-run without --reset: reuse the existing password so credentials still authenticate.
        password = str(json.loads(credentials.read_text(encoding="utf-8"))["password"])
    else:
        password = secrets.token_urlsafe(DEMO_PASSWORD_LENGTH)
        for username, role in (("demo-admin", "admin"), ("demo-viewer", "viewer")):
            if get_user_by_name(username, db) is None:
                create_user(username, password, role, db)
        # Create mode-0600 directly (no world-readable window between write and chmod).
        descriptor = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {"username": "demo-admin", "viewer": "demo-viewer", "password": password},
                handle,
            )

    if get_setting("demo.seeded", db):
        events_new = 0
    else:
        files = _files(target, reference)
        # The settings file was written before auth.log existed; rewrite it so the path is accurate.
        settings_path = _settings(target, db, files["auth_log"])
        settings = load_settings(config_path=settings_path)
        from storage.severity_repository import add_allowlist_entry

        add_allowlist_entry(
            {
                "kind": "ip",
                "value": "192.0.2.10",
                "scope": "suppress_alerts",
                "reason": "trusted demo monitoring host",
            },
            "demo",
            db,
        )
        _monitor_paths(db, files, reference)
        _synthetic_events(db, reference)
        # Local file sink: demonstrates notifications without any outbound network call.
        from storage.notification_repository import add_channel

        add_channel(
            {
                "name": "Demo file sink",
                "kind": "file",
                "enabled": True,
                "config": {"path": str(target / "logs" / "notifications.jsonl")},
                "min_severity": "low",
            },
            "demo",
            db,
        )
        set_setting("notifications.enabled", True, updated_by="demo", db_path=db)
        # Demonstrate drift by changing metadata after the baseline was captured.
        os.chmod(files["sshd"], 0o777)  # noqa: S103 - intentional demo drift evidence
        files["cron"].write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
        files["authorized_keys"].write_text(
            files["authorized_keys"].read_text(encoding="utf-8")
            + _fake_key_line("demo-added", secrets.token_hex(6)),
            encoding="utf-8",
        )
        run_once(settings, db, reference, notify=True)
        run_once(settings, db, reference + timedelta(seconds=1), notify=True)
        set_setting("demo.seeded", True, updated_by="demo", db_path=db)
        events_new = count_events(db_path=db)

    incidents = list_incidents(db_path=db)
    # The richest incident is the one the demo exists to showcase; anomalies
    # from the baseline cycle can create smaller single-event incidents too.
    incidents.sort(key=lambda item: len(item.get("event_ids") or []), reverse=True)
    assessment = get_assessment("incident", incidents[0]["id"], db) if incidents else None
    findings = query_events({"event_type": ["rule_triggered"]}, db_path=db)["items"]
    summary = {
        "events": count_events(db_path=db),
        "events_new": events_new,
        "incidents": len(incidents),
        "findings": len(findings),
        "score": assessment["score"] if assessment else 0,
        "severity": assessment["severity"] if assessment else "low",
        "workdir": str(target),
    }
    if print_password:
        print("Sentinel demo created at", target)
        print("Demo admin: demo-admin")
        print("One-time password:", password)
        print("Viewer:", "demo-viewer")
        print("Summary:", json.dumps(summary, sort_keys=True))
        print("Start the API (from the project root):")
        print(
            f"  SENTINEL_SESSION_KEY=$(cat {target / 'session.key'}) "
            f"SENTINEL_CONFIG={settings_path} ./venv/bin/uvicorn api.main:app "
            f"--host 127.0.0.1 --port 8000"
        )
        print("Start the web: cd web && npm run start")
        _print_demo_details(target, incidents, findings, assessment, db, reference)
    else:
        print("Summary:", json.dumps(summary, sort_keys=True))
    if live:
        _demo_live(target)
    return summary


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    reset = "--reset" in args
    quiet = "--no-print-password" in args
    live = "--live" in args
    workdir = DEFAULT_WORKDIR
    if "--workdir" in args:
        index = args.index("--workdir")
        if index + 1 < len(args):
            workdir = args[index + 1]
    build_demo(workdir, reset=reset, print_password=not quiet, live=live)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
