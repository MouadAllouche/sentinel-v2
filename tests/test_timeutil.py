"""Tests for pure time helpers (Phase 0)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from core import timeutil


def test_utc_now_is_aware_and_utc() -> None:
    value = timeutil.utc_now()
    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(0)


def test_to_utc_iso_normalises_aware_inputs() -> None:
    assert (
        timeutil.to_utc_iso("2026-11-15T01:24:19.424500+00:00")
        == "2026-11-15T01:24:19.424500+00:00"
    )
    aware = datetime(2026, 11, 15, 2, 24, 19, tzinfo=timezone(timedelta(hours=1)))
    assert timeutil.to_utc_iso(aware) == "2026-11-15T01:24:19+00:00"
    assert timeutil.to_utc_iso("2026-11-15T01:24:19Z") == "2026-11-15T01:24:19+00:00"


def test_to_utc_iso_naive_uses_injected_local_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timeutil, "_local_tzinfo", lambda: timezone(timedelta(hours=1)))
    assert (
        timeutil.to_utc_iso("2026-11-15T10:00:00", assume_local=True) == "2026-11-15T09:00:00+00:00"
    )
    assert (
        timeutil.to_utc_iso("2026-11-15T10:00:00", assume_local=False)
        == "2026-11-15T10:00:00+00:00"
    )


def test_to_utc_iso_explicit_timezone_overrides_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timeutil, "_local_tzinfo", lambda: timezone(timedelta(hours=1)))
    value = timeutil.to_utc_iso("2026-11-15T10:00:00", tz=timezone(timedelta(hours=-5)))
    assert value == "2026-11-15T15:00:00+00:00"


def test_to_utc_iso_syslog_prefix_with_explicit_year() -> None:
    assert timeutil.to_utc_iso("Nov  4 10:30:15", year=2026, tz=UTC) == "2026-11-04T10:30:15+00:00"


def test_to_utc_iso_syslog_year_inferred_from_injected_now() -> None:
    now = datetime(2027, 1, 2, 0, 0, tzinfo=UTC)
    assert timeutil.to_utc_iso("Dec 31 23:30:15", now=now, tz=UTC) == "2026-12-31T23:30:15+00:00"


def test_to_utc_iso_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="timestamp"):
        timeutil.to_utc_iso("garbage")
    with pytest.raises(ValueError, match="timestamp"):
        timeutil.to_utc_iso(123)  # type: ignore[arg-type]


def test_parse_ts_returns_aware_datetime() -> None:
    parsed = timeutil.parse_ts("2026-11-15T01:24:19+00:00")
    assert parsed == datetime(2026, 11, 15, 1, 24, 19, tzinfo=UTC)
    naive = timeutil.parse_ts("2026-11-15T01:24:19", assume_local=False)
    assert naive.utcoffset() == timedelta(0)
    with pytest.raises(ValueError):
        timeutil.parse_ts("not a date")


def test_floor_hour_keeps_timezone_and_truncates() -> None:
    value = datetime(2026, 11, 15, 12, 34, 56, 123456, tzinfo=UTC)
    assert timeutil.floor_hour(value) == datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)
    other = datetime(2026, 11, 15, 12, 34, tzinfo=timezone(timedelta(hours=1)))
    assert timeutil.floor_hour(other).utcoffset() == timedelta(hours=1)
    assert timeutil.floor_hour(other).minute == 0


def test_window_bounds_returns_start_and_end() -> None:
    end = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    start, stop = timeutil.window_bounds(end, 600)
    assert stop == end
    assert start == end - timedelta(seconds=600)
    naive_end = datetime(2026, 11, 15, 12, 0)
    assert timeutil.window_bounds(naive_end, 60, assume_local=False)[0] == datetime(
        2026, 11, 15, 11, 59, tzinfo=UTC
    )
