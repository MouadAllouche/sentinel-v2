"""Pure scheduler state machine. No sleeping, clock or I/O."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

__all__ = ["SchedulerState", "next_due", "record_result"]


@dataclass(frozen=True)
class SchedulerState:
    last_collect: datetime | None = None
    last_analyze: datetime | None = None
    collect_interval: int = 60
    analyze_interval: int = 120
    retention_interval_hours: int = 24
    consecutive_failures: int = 0
    backoff_base: int = 10
    jitter_seconds: int = 0
    use_jitter: bool = False
    shutdown: bool = False


def next_due(state: SchedulerState, now: datetime, nonce: int = 0) -> datetime | None:
    """Return the next due time, or None when shutting down."""
    if state.shutdown:
        return None
    if state.last_collect is None and state.last_analyze is None:
        return now
    backoff = state.consecutive_failures * state.backoff_base * 2
    far_future = datetime.max.replace(tzinfo=UTC)
    collect_due = (
        (state.last_collect + timedelta(seconds=state.collect_interval + backoff))
        if state.last_collect
        else far_future
    )
    analyze_due = (
        (state.last_analyze + timedelta(seconds=state.analyze_interval + backoff))
        if state.last_analyze
        else far_future
    )
    due = min(collect_due, analyze_due)
    if state.use_jitter and state.jitter_seconds > 0:
        due += timedelta(seconds=nonce % (state.jitter_seconds + 1))
    return due


def record_result(
    state: SchedulerState, component: str, *, ok: bool, now: datetime
) -> SchedulerState:
    """Update the state after a component run."""
    failures = 0 if ok else state.consecutive_failures + 1
    if component == "collect":
        return replace(state, last_collect=now, consecutive_failures=failures)
    if component == "analyze":
        return replace(state, last_analyze=now, consecutive_failures=failures)
    return replace(state, consecutive_failures=failures)
