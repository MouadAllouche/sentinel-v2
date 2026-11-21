"""Phase 19 security verification: no outbound traffic and no stored secrets."""

from __future__ import annotations

import json
import smtplib
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from core.config import load_settings
from engine.runner import run_once
from scripts.demo import build_demo
from storage.database import init_db
from storage.repositories import query_events_bulk

NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)


def test_default_config_is_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A full cycle with the *real* defaults must never open a socket.

    Collectors are stubbed at the I/O boundary only (tests never read real logs
    or network state). The notifier is deliberately left enabled: the default
    config has ``notifications.enabled = false`` and no channels in the DB, so
    the outbound transports must remain unused.
    """
    db = tmp_path / "offline.db"
    init_db(db)
    settings = load_settings(config_path=None)
    assert settings.notifications.enabled is False
    monkeypatch.setattr("engine.ingest._collector_specs", lambda _settings, _now: [])

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("outbound network call attempted by default config")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "gethostbyname", forbidden)
    monkeypatch.setattr(smtplib, "SMTP", forbidden)
    monkeypatch.setattr(httpx, "post", forbidden)

    report = run_once(settings, db, NOW, notify=True)
    assert report.ok, report


def test_demo_db_stores_no_secrets_contents_or_command_lines(tmp_path: Path) -> None:
    workdir = tmp_path / "demo"
    build_demo(workdir, now=NOW, print_password=False)
    credentials = json.loads((workdir / "credentials.json").read_text(encoding="utf-8"))
    password = str(credentials["password"])
    session_key = (workdir / "session.key").read_text(encoding="utf-8").strip()

    events = query_events_bulk({}, db_path=workdir / "demo.db")
    blob = json.dumps(events, sort_keys=True).lower()
    # The actual planted secrets must not appear anywhere in stored events.
    assert password.lower() not in blob
    assert session_key.lower() not in blob
    for forbidden in ("cmdline", "password=", "secret=", "ssh-ed25519 ", "/etc/shadow"):
        assert forbidden not in blob, f"stored data contains {forbidden}"
