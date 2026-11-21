"""Regression tests for the demo/spec gaps fixed after Phase 18.

Everything here runs against a sandboxed demo generated in ``tmp_path``; no real
system file, network or clock is touched (a fixed ``NOW`` is used).
"""

from __future__ import annotations

import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from scripts.demo import build_demo
from storage.repositories import query_events

NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)
SESSION_KEY = "a-test-session-key-with-at-least-32-chars"


def _demo(tmp_path: Path, *, show: bool = False) -> tuple[Path, Any]:
    workdir = tmp_path / "demo"
    captured = build_demo(workdir, now=NOW, print_password=show)
    return workdir, captured


def test_demo_prints_every_grouping_reason(tmp_path: Path, capsys: Any) -> None:
    _demo(tmp_path, show=True)
    out = capsys.readouterr().out
    assert "Grouping reasons:" in out
    strong = [line.strip() for line in out.splitlines() if line.strip().startswith("strong:")]
    weak = [line.strip() for line in out.splitlines() if line.strip().startswith("weak:")]
    assert strong, "no strong link reasons printed"
    assert weak, "no weak link reasons printed"
    # No silent truncation of the explanation.
    assert len(strong) > 3 or len(weak) > 3 or "…" not in out


def test_demo_incident_explanation_api_has_strong_and_weak_reasons(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from api.main import create_app

    workdir, _ = _demo(tmp_path)
    monkeypatch.setenv("SENTINEL_SESSION_KEY", SESSION_KEY)
    app = create_app(db_path=str(workdir / "demo.db"))
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": "demo-admin",
                "password": json.loads((workdir / "credentials.json").read_text())["password"],
            },
        )
        assert login.status_code == 200, login.text
        incidents = client.get("/api/incidents").json()["items"]
        assert incidents
        # The baseline anomaly can create its own small incident; explain the
        # main grouped one.
        incidents.sort(key=lambda item: len(item.get("event_ids") or []), reverse=True)
        payload = client.get(f"/api/incidents/{incidents[0]['id']}/explanation").json()
    assert payload["grouping"]["strong"], "API returned no strong link reasons"
    assert payload["grouping"]["weak"], "API returned no weak link reasons"


def test_demo_anomaly_comes_from_the_real_baseline_pipeline(tmp_path: Path) -> None:
    workdir, _ = _demo(tmp_path)
    db = workdir / "demo.db"
    anomalies = query_events({"event_type": ["anomaly"]}, db_path=db)["items"]
    assert anomalies, "baseline cycle emitted no anomaly event"
    item = anomalies[0]
    assert item["source"] == "baseline"
    details = item["details"]
    assert details["metric"] == "failed_logins_per_hour"
    assert details["sample_count"] >= 24
    assert details["window_start"] and details["window_end"]
    assert details["z_observed"] > 0
    # Seven days of benign history precede the spike (spec 08).
    benign = query_events({"event_type": ["failed_login"]}, db_path=db, limit=500)["items"]
    oldest_benign = min(
        event["timestamp"] for event in benign if event.get("source_ip") == "198.51.100.7"
    )
    assert oldest_benign <= (NOW - timedelta(days=7) + timedelta(seconds=1)).isoformat()
    description = item["description"]
    for fragment in (
        "observed",
        "mean",
        "std",
        "hourly samples",
        "standard deviations above normal",
    ):
        assert fragment in description, f"missing explanation fragment: {fragment}"
    assert "far above the expected band" not in description
    # Idempotence: a repeat cycle must not create a second anomaly for the same hour.
    from core.config import load_settings
    from engine.runner import run_once

    run_once(load_settings(config_path=workdir / "settings.toml"), db, NOW, notify=False)
    assert len(query_events({"event_type": ["anomaly"]}, db_path=db)["items"]) == len(anomalies)


def test_demo_authorized_keys_drift_names_key_fingerprints(tmp_path: Path) -> None:
    workdir, _ = _demo(tmp_path)
    db = workdir / "demo.db"
    drift = query_events({"event_type": ["config_drift"]}, db_path=db)["items"]
    key_drift = [item for item in drift if "authorized_keys" in item["description"]]
    assert key_drift, "no authorized_keys drift event"
    joined = " ".join(item["description"] for item in key_drift)
    assert "key added (SHA256:" in joined
    assert "ssh-ed25519" not in joined, "drift must never expose key material"


def test_demo_writes_private_mode_0600_session_key(tmp_path: Path, capsys: Any) -> None:
    workdir, _ = _demo(tmp_path, show=True)
    out = capsys.readouterr().out
    key_path = workdir / "session.key"
    assert key_path.exists()
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert len(key_path.read_text(encoding="utf-8").strip()) >= 32
    assert "session.key" in out
    assert f"SENTINEL_SESSION_KEY=$(cat {key_path})" in out, (
        "printed command must be shell-pasteable"
    )
    assert "demo-session-key-0123456789abcdef" not in out


def test_no_literal_demo_session_keys_in_tooling() -> None:
    root = Path(__file__).resolve().parents[1]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    playwright = (root / "web" / "playwright.config.ts").read_text(encoding="utf-8")
    assert "demo-session-key-" not in makefile
    assert "e2e-session-key-" not in playwright
    assert "session.key" in makefile
    assert "session.key" in playwright
