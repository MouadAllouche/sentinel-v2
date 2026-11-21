"""Tests for the sandboxed demo generator (Phase 18)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.demo import build_demo
from storage.incident_repository import list_incidents
from storage.repositories import count_events, query_events
from storage.risk_repository import get_assessment

NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)


def test_demo_creates_sandbox_and_is_idempotent(tmp_path: Path) -> None:
    workdir = tmp_path / "demo"
    first = build_demo(workdir, now=NOW, print_password=False)
    assert (workdir / "auth.log").exists()
    assert (workdir / "etc" / "sshd_config").exists()
    assert (workdir / "etc" / "cron.d" / "backup").exists()
    assert (workdir / "demo.db").exists()
    assert (workdir / "settings.toml").exists()
    credentials = json.loads((workdir / "credentials.json").read_text())
    assert len(credentials["password"]) >= 12
    assert first["events"] >= 25
    assert first["incidents"] >= 1

    before = count_events(db_path=workdir / "demo.db")
    second = build_demo(workdir, now=NOW, print_password=False)
    assert second["events_new"] == 0
    assert count_events(db_path=workdir / "demo.db") == before


def test_demo_records_expected_tiers_and_drift(tmp_path: Path) -> None:
    workdir = tmp_path / "demo"
    build_demo(workdir, now=NOW, print_password=False)
    db = workdir / "demo.db"
    findings = query_events({"event_type": ["rule_triggered"]}, db_path=db)["items"]
    assert any(item.get("severity") == "critical" for item in findings)
    drift = query_events({"event_type": ["config_drift"]}, db_path=db)["items"]
    assert drift
    incidents = list_incidents(db_path=db)
    assert incidents
    assessment = get_assessment("incident", incidents[0]["id"], db)
    assert assessment is not None
    assert assessment["score"] >= 0


def test_demo_refuses_monitored_system_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_demo(tmp_path / "etc" / "demo", now=NOW, print_password=False)
