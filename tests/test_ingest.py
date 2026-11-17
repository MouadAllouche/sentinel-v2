"""Tests for ingestion orchestration (Phase 3)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from collectors import CollectionResult
from core.config import load_settings
from core.timeutil import utc_now
from engine import ingest
from storage.database import get_connection
from storage.repositories import count_events, get_state


def _settings(db: Path, **collector_overrides: bool) -> Any:
    base = load_settings(
        env={"SENTINEL_DB_PATH": str(db)}, root=Path(__file__).resolve().parents[1]
    )
    disabled = {
        "network": False,
        "listening": False,
        "processes": False,
        "filesystem": False,
        "dpkg": False,
        "system": False,
    }
    disabled.update(collector_overrides)
    return replace(base, collectors=replace(base.collectors, auth_source="auth_log", **disabled))


def _runs(db: Path) -> list[Any]:
    connection = get_connection(db)
    rows = connection.execute(
        "SELECT collector, status, events_found, events_new FROM collector_runs ORDER BY id"
    ).fetchall()
    connection.close()
    return list(rows)


def test_collection_is_idempotent_and_state_saved_after_events(
    tmp_initialised_db: Path,
    make_event: Callable[..., dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_initialised_db)
    calls: list[int] = []

    def fake_collect(path: object, state: object, now: object = None) -> CollectionResult:
        calls.append(1)
        return CollectionResult(
            events=[make_event(description="ingested")],
            warnings=[],
            state={"offset": 10},
        )

    monkeypatch.setattr(ingest, "collect_auth_events", fake_collect)
    now = datetime(2026, 11, 15, 10, tzinfo=UTC)
    first = ingest.run_collection(settings, tmp_initialised_db, now=now)
    assert first.events_new == 1
    assert count_events({}, tmp_initialised_db) == 1
    key = "auth_log:" + str(settings.paths.auth_log)
    assert get_state(key, tmp_initialised_db) == {"offset": 10}
    assert _runs(tmp_initialised_db)[0]["status"] == "ok"

    second = ingest.run_collection(settings, tmp_initialised_db, now=now)
    assert second.events_new == 0
    assert count_events({}, tmp_initialised_db) == 1
    assert len(calls) == 2


def test_state_not_saved_when_write_fails(
    tmp_initialised_db: Path,
    make_event: Callable[..., dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_initialised_db)
    monkeypatch.setattr(
        ingest,
        "collect_auth_events",
        lambda path, state, now=None: CollectionResult(
            events=[make_event()], warnings=[], state={"offset": 99}
        ),
    )

    def fail_save(*args: object, **kwargs: object) -> object:
        raise RuntimeError("disk full")

    monkeypatch.setattr(ingest, "save_events", fail_save)
    ingest.run_collection(settings, tmp_initialised_db, now=utc_now())
    key = "auth_log:" + str(settings.paths.auth_log)
    assert get_state(key, tmp_initialised_db) is None
    assert _runs(tmp_initialised_db)[0]["status"] == "error"


def test_one_failing_collector_does_not_stop_others(
    tmp_initialised_db: Path,
    make_event: Callable[..., dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_initialised_db, dpkg=True)
    monkeypatch.setattr(
        ingest,
        "collect_auth_events",
        lambda path, state, now=None: CollectionResult(
            events=[make_event(description="auth ok")], warnings=[], state={"offset": 1}
        ),
    )

    def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError("dpkg unavailable")

    monkeypatch.setattr(ingest, "collect_dpkg_events", broken)
    report = ingest.run_collection(settings, tmp_initialised_db, now=utc_now())
    assert report.events_new == 1
    runs = _runs(tmp_initialised_db)
    assert {row["collector"]: row["status"] for row in runs} == {
        "auth_log": "ok",
        "dpkg": "error",
    }


def test_empty_collection_records_ok_run(
    tmp_initialised_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_initialised_db)
    base = load_settings(env={}, root=Path(__file__).resolve().parents[1])
    settings = replace(
        settings,
        collectors=replace(
            base.collectors,
            auth_source="auth_log",
            network=False,
            listening=False,
            processes=False,
            filesystem=False,
            dpkg=False,
            system=False,
        ),
    )
    # Disable auth_log by pointing it at a path the fake collector reports no events for.
    monkeypatch.setattr(
        ingest,
        "collect_auth_events",
        lambda path, state, now=None: CollectionResult(events=[], warnings=[], state={}),
    )
    report = ingest.run_collection(settings, tmp_initialised_db, now=utc_now())
    assert report.events_new == 0
