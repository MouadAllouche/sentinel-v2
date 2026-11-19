"""Tests for the pure scheduler state machine (Phase 11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from engine.scheduler import SchedulerState, next_due, record_result

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def test_initial_due_is_now() -> None:
    state = SchedulerState()
    assert next_due(state, NOW) == NOW


def test_next_due_after_collect_and_analyze() -> None:
    state = SchedulerState(
        last_collect=NOW, last_analyze=NOW, collect_interval=60, analyze_interval=120
    )
    assert next_due(state, NOW + timedelta(seconds=10)) == NOW + timedelta(seconds=60)


def test_jitter_is_bounded_and_deterministic() -> None:
    state = SchedulerState(last_collect=NOW, jitter_seconds=5, use_jitter=True)
    due = next_due(state, NOW, nonce=7)
    assert NOW + timedelta(seconds=60) <= due <= NOW + timedelta(seconds=65)
    assert next_due(state, NOW, nonce=7) == due


def test_backoff_on_repeated_failures() -> None:
    state = SchedulerState(last_collect=NOW, consecutive_failures=2, backoff_base=10)
    due = next_due(state, NOW)
    assert due >= NOW + timedelta(seconds=60 + 40)


def test_shutdown_flag_stops_scheduling() -> None:
    state = SchedulerState(shutdown=True)
    assert next_due(state, NOW) is None


def test_record_result_resets_or_increments_failures() -> None:
    state = SchedulerState(consecutive_failures=2)
    failed = record_result(state, "collect", ok=False, now=NOW)
    assert failed.consecutive_failures == 3
    recovered = record_result(failed, "collect", ok=True, now=NOW)
    assert recovered.consecutive_failures == 0
