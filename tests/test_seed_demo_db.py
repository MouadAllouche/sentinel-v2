"""Tests for the deterministic demo-database seed used by Playwright."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.seed_demo_db import seed
from storage.auth_repository import get_user_by_name
from storage.repositories import count_events


def test_seed_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "demo.db"
    first = seed(db, "demo-password-123", now="2026-11-19T12:00:00+00:00")
    assert first["events"] >= 10
    assert count_events(db_path=db) == first["events"]
    assert get_user_by_name("admin", db) is not None
    assert get_user_by_name("viewer", db) is not None

    second = seed(db, "demo-password-123", now="2026-11-19T12:00:00+00:00")
    assert second == first
    assert count_events(db_path=db) == first["events"]


def test_seed_refuses_monitored_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        seed(tmp_path / "etc" / "sentinel.db", "demo-password-123")
