"""Shared test fixtures.

Every test runs with the database and config paths redirected into a temporary
directory before any application code is imported or called. Tests never touch
the real DB, /etc, /var/log, the network or the real clock.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from storage.database import init_db

_FIXED_NOW = datetime(2026, 11, 15, 12, 34, 56, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point all path-bearing environment variables at the test sandbox."""
    monkeypatch.setenv("SENTINEL_DB_PATH", str(tmp_path / "sentinel.db"))
    monkeypatch.setenv("SENTINEL_CONFIG", str(tmp_path / "settings.toml"))
    monkeypatch.delenv("SENTINEL_SESSION_KEY", raising=False)


@pytest.fixture
def NOW() -> datetime:  # noqa: N802 - the spec names this fixture NOW
    """A fixed, UTC-aware timestamp for time-dependent code."""
    return _FIXED_NOW


@pytest.fixture
def now() -> datetime:
    """Lowercase alias of the NOW fixture."""
    return _FIXED_NOW


@pytest.fixture
def make_event() -> Callable[..., dict[str, object]]:
    """Build a minimal valid event, with overrides."""

    def _make(**overrides: object) -> dict[str, object]:
        event: dict[str, object] = {
            "timestamp": "2026-11-15T10:00:00+00:00",
            "source": "auth_log",
            "event_type": "failed_login",
            "severity": "low",
            "description": "Failed SSH login attempt for admin",
            "username": "admin",
            "source_ip": "203.0.113.45",
        }
        event.update(overrides)
        return event

    return _make


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """A path to a throwaway database file.

    The file is deliberately not shared with the real project database.
    """
    return tmp_path / "sentinel.db"


@pytest.fixture
def tmp_initialised_db(tmp_db: Path) -> Path:
    """An initialised, empty database in the test sandbox."""
    init_db(db_path=tmp_db)
    return tmp_db


@pytest.fixture
def api_client(tmp_initialised_db: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """A FastAPI TestClient bound to a throwaway database and session key."""
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.setenv("SENTINEL_SESSION_KEY", "a-test-session-key-with-at-least-32-chars")
    app = create_app(db_path=tmp_initialised_db)
    with TestClient(app) as client:
        yield client
