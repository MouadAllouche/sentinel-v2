"""Generate and verify committed web fixtures from the real API (Phase 18 fix).

The JSON files under ``web/tests/fixtures`` are produced by running the API
against a deterministic, seeded temporary database via ``TestClient``. They are
the single source of truth for Vitest/MSW tests, so mocks cannot drift from the
contract. ``test_api_fixtures_are_current`` fails when they are stale.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.main import create_app
from core.baseline import Baseline
from core.config import CollectorSettings, load_settings
from engine.runner import run_once
from storage.auth_repository import create_user
from storage.baseline_repository import save_baseline
from storage.database import init_db
from storage.drift_repository import add_monitored_path, save_snapshot
from storage.repositories import save_events
from storage.rules_repository import seed_rules
from storage.severity_repository import add_allowlist_entry, seed_defaults

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "web" / "tests" / "fixtures"
PASSWORD = "a-very-long-fixture-password"
NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
NAMES = (
    "incidents",
    "incident",
    "events",
    "rules",
    "findings",
    "baselines",
    "drift",
    "health",
    "collectors",
    "channels",
    "thresholds",
    "systemInfo",
    "stats",
    "top",
    "changes",
    "timeline",
    "explanation",
    "graph",
    "notes",
    "history",
)


def _event(identifier: int, seconds: int, event_type: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": identifier,
        "timestamp": (NOW + timedelta(seconds=seconds)).isoformat(),
        "source": "auth_log",
        "event_type": event_type,
        "severity": "low",
        "description": f"{event_type} from 203.0.113.45",
        "username": "admin",
        "source_ip": "203.0.113.45",
    }
    result.update(extra)
    return result


def build_fixture_db(db_path: Path) -> Path:
    """A deterministic DB with a realistic incident, drift and baseline data."""
    init_db(db_path)
    seed_defaults(db_path)
    seed_rules(db_path)
    create_user("fixture-admin", PASSWORD, "admin", db_path)
    add_allowlist_entry(
        {
            "kind": "ip",
            "value": "192.0.2.10",
            "scope": "suppress_alerts",
            "reason": "trusted fixture monitoring host",
        },
        "fixture",
        db_path,
    )
    events = [_event(index + 1, index, "failed_login") for index in range(30)]
    events += [
        _event(100, 40, "successful_login"),
        _event(101, 45, "sudo_command", process_name="sudo"),
        _event(
            102,
            50,
            "config_drift",
            source="filesystem",
            file_path="/etc/ssh/sshd_config",
            severity="high",
        ),
        _event(
            103,
            55,
            "network_connection",
            source="network",
            process_name="ssh",
            destination_ip="192.0.2.10",
            destination_port=443,
        ),
        _event(104, 60, "package_installed", source="dpkg", process_name="apt"),
        _event(
            105,
            65,
            "anomaly",
            source="baseline",
            severity="medium",
            description="failed_login count far above the expected band",
        ),
        _event(106, 70, "failed_login", source_ip="192.0.2.10", username="monitor"),
    ]
    save_events(events, db_path, allowlisted=False)
    save_events([events[-1]], db_path, allowlisted=True)

    add_monitored_path(
        {
            "path": "/etc/ssh/sshd_config",
            "kind": "file",
            "category": "ssh",
            "sensitivity": "high",
            "enabled": True,
        },
        "fixture",
        db_path,
        allow_custom_paths=True,
    )
    snapshot = {
        "path": "/etc/ssh/sshd_config",
        "exists": True,
        "kind": "file",
        "sha256": "a" * 64,
        "owner": "root",
        "group": "root",
        "mode": "0644",
        "mtime": NOW.isoformat(),
        "size": 128,
        "is_symlink": False,
        "extra": {},
        "captured_at": NOW.isoformat(),
    }
    save_snapshot(snapshot, is_baseline=True, db_path=db_path)
    save_baseline(
        Baseline(
            metric="failed_logins_per_hour",
            subject="global",
            window_start=(NOW - timedelta(days=1)).isoformat(),
            window_end=NOW.isoformat(),
            mean=2.0,
            stddev=0.5,
            sample_count=24,
            maximum=3.0,
            p95=3.0,
            maturity="mature",
            reason="",
        ),
        db_path,
    )
    base = load_settings(config_path=None)
    settings = replace(
        base,
        collectors=CollectorSettings(
            auth_source="auth_log",
            journald_unit="ssh",
            network=False,
            listening=False,
            processes=False,
            filesystem=False,
            dpkg=False,
            system=False,
            max_process_events_per_run=0,
        ),
    )
    run_once(settings, db_path, NOW, notify=False)
    return db_path


def _normalise(value: Any) -> Any:
    """Replace timestamps produced by the real clock with the fixed fixture NOW."""
    if isinstance(value, dict):
        return {
            key: NOW.isoformat()
            if key in {"created_at", "updated_at", "computed_at", "generated_at", "at"}
            else _normalise(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    return value


def dump_fixtures(db_path: Path, monkeypatch: Any) -> dict[str, Any]:
    monkeypatch.setenv("SENTINEL_SESSION_KEY", "fixture-session-key-0123456789abcdef")
    app = create_app(db_path=str(db_path))
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "fixture-admin", "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        endpoints = {
            "incidents": "/api/incidents",
            "incident": "/api/incidents/1",
            "events": "/api/events?limit=100",
            "rules": "/api/rules",
            "findings": "/api/rules/findings",
            "baselines": "/api/baselines",
            "drift": "/api/drift/status",
            "health": "/api/health",
            "collectors": "/api/collectors",
            "channels": "/api/notifications/channels",
            "thresholds": "/api/risk/thresholds",
            "systemInfo": "/api/system/info",
            "stats": "/api/events/stats?bucket=hour",
            "top": "/api/events/top?field=event_type&limit=50",
            "changes": "/api/changes?since=0",
            "timeline": "/api/incidents/1/timeline",
            "explanation": "/api/incidents/1/explanation",
            "graph": "/api/incidents/1/graph",
            "notes": "/api/incidents/1/notes",
            "history": "/api/incidents/1/history",
        }
        return {name: _normalise(client.get(path).json()) for name, path in endpoints.items()}


def test_generate_api_fixtures(tmp_path: Path, monkeypatch: Any) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    data = dump_fixtures(build_fixture_db(tmp_path / "fixtures.db"), monkeypatch)
    for name, payload in data.items():
        (FIXTURES / f"{name}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def test_api_fixtures_are_current(tmp_path: Path, monkeypatch: Any) -> None:
    expected = dump_fixtures(build_fixture_db(tmp_path / "fixtures.db"), monkeypatch)
    stale = []
    for name in NAMES:
        path = FIXTURES / f"{name}.json"
        if not path.exists():
            stale.append(f"{name}.json (missing)")
            continue
        committed = json.loads(path.read_text(encoding="utf-8"))
        if committed != expected[name]:
            stale.append(f"{name}.json (stale)")
    assert stale == [], (
        "regenerate fixtures with: "
        "pytest tests/test_api_fixtures.py::test_generate_api_fixtures "
        f"-> {stale}"
    )


def test_fixtures_have_representative_shapes() -> None:
    incidents = json.loads((FIXTURES / "incidents.json").read_text(encoding="utf-8"))["items"]
    assert incidents
    assert all("mitre" in item for item in incidents)
    detail = json.loads((FIXTURES / "incident.json").read_text(encoding="utf-8"))
    assert {"id", "title", "status", "severity", "mitre"}.issubset(detail)
    events = json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))["items"]
    assert any(item["event_type"] == "config_drift" for item in events)
    findings = json.loads((FIXTURES / "findings.json").read_text(encoding="utf-8"))
    assert findings
