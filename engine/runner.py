"""Engine daemon orchestration and single-cycle runner."""

from __future__ import annotations

import json
import signal
import time
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.config import Settings
from core.pipeline import CycleReport, run_cycle
from core.timeutil import utc_now
from engine.baselines import run_baselines
from engine.correlation import run_correlation
from engine.drift import check_drift
from engine.ingest import run_collection
from engine.notifier import run_notifier
from engine.rules import run_rules
from engine.scheduler import SchedulerState, next_due, record_result
from engine.scoring import run_scoring
from storage.database import get_connection
from storage.repositories import get_setting, set_setting
from storage.rules_repository import seed_rules
from storage.severity_repository import seed_defaults

LOCK_KEY = "engine.lock"


def _collect(settings: Settings, db_path: str | Path | None, now: datetime) -> dict[str, Any]:
    report = run_collection(settings, db_path, now=now)
    drift = check_drift(db_path, now=now)
    return {"events_new": report.events_new, "drift_events": drift.drift_events}


def default_steps(
    settings: Settings, *, notify: bool = True
) -> list[tuple[str, Callable[..., Any]]]:
    """The eight pipeline steps in spec order (notify/publish are isolated)."""
    steps: list[tuple[str, Callable[..., Any]]] = [
        ("collect", _collect),
        ("rules", lambda _s, db, now: {"findings_new": run_rules(db, now=now).findings_new}),
        ("baselines", lambda _s, db, now: {"anomalies": run_baselines(db, now=now).anomalies_new}),
        (
            "correlation",
            lambda _s, db, now: {"created": run_correlation(db, now=now).incidents_created},
        ),
        ("score", lambda _s, db, now: {"assessments": run_scoring(db, now=now).assessments}),
    ]

    def notify_step(settings: Settings, db: str | Path | None, now: datetime) -> dict[str, Any]:
        if not notify:
            return {"skipped": True}
        return run_notifier(db, now=now, settings=settings)

    def publish_step(_settings: Settings, db: str | Path | None, now: datetime) -> dict[str, Any]:
        with closing(get_connection(db)) as connection:
            connection.execute(
                "INSERT INTO changes(kind, ref_id, at) VALUES (?, ?, ?)",
                ("cycle.completed", 0, now.isoformat()),
            )
            connection.commit()
        return {"published": True}

    steps.extend([("notify", notify_step), ("publish", publish_step)])
    return steps


def acquire_lock(db_path: str | Path | None, *, owner: str, now: datetime | None = None) -> bool:
    reference = now or utc_now()
    current = get_setting(LOCK_KEY, db_path) or {}
    expires = current.get("expires")
    if expires and datetime.fromisoformat(expires) <= reference:
        current = {}
    if current and current.get("owner") != owner:
        return False
    set_setting(
        LOCK_KEY,
        {"owner": owner, "expires": (reference + timedelta(minutes=10)).isoformat()},
        updated_by=owner,
        db_path=db_path,
    )
    return True


def release_lock(db_path: str | Path | None, *, owner: str) -> None:
    current = get_setting(LOCK_KEY, db_path) or {}
    if current.get("owner") == owner:
        set_setting(LOCK_KEY, {}, updated_by=owner, db_path=db_path)


def run_once(
    settings: Settings,
    db_path: str | Path | None,
    now: datetime | None = None,
    *,
    notify: bool = True,
    steps: list[tuple[str, Any]] | None = None,
) -> CycleReport:
    """Run one full cycle; safe to call repeatedly."""
    reference = now or utc_now()
    seed_defaults(db_path)
    seed_rules(db_path)
    selected = steps or default_steps(settings, notify=notify)
    report = run_cycle(settings, db_path, now=reference, steps=selected)
    with closing(get_connection(db_path)) as connection:
        connection.execute(
            "INSERT INTO cycle_runs(started_at, finished_at, status, steps_json) "
            "VALUES (?, ?, ?, ?)",
            (
                reference.isoformat(),
                utc_now().isoformat(),
                "ok" if report.ok else "error",
                json.dumps([s.__dict__ for s in report.steps], default=str),
            ),
        )
        connection.commit()
    return report


def run_engine_loop(
    settings: Settings,
    db_path: str | Path | None,
    *,
    once: bool = False,
    no_notify: bool = False,
    shutdown: Callable[[], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Loop until shutdown/once; returns a process exit code."""
    state = SchedulerState(
        collect_interval=settings.engine.collect_interval_seconds,
        analyze_interval=settings.engine.analyze_interval_seconds,
    )
    iteration = 0
    while not (shutdown and shutdown()):
        reference = utc_now()
        if not acquire_lock(db_path, owner="engine", now=reference):
            sleep(1)
            continue
        try:
            report = run_once(settings, db_path, reference, notify=not no_notify)
        finally:
            release_lock(db_path, owner="engine")
        iteration += 1
        if once:
            break
        state = record_result(state, "collect", ok=report.ok, now=reference)
        state = record_result(state, "analyze", ok=report.ok, now=reference)
        due = next_due(state, reference, nonce=iteration)
        if due is None:
            break
        sleep(max(0.0, (due - utc_now()).total_seconds()))
        if iteration > 10_000:  # pragma: no cover - defensive loop bound
            break
    return 0


def handle_signal(signum: int, frame: Any) -> None:  # pragma: no cover - OS signal path
    raise SystemExit(0)


def install_signal_handlers() -> None:  # pragma: no cover - OS signal path
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
