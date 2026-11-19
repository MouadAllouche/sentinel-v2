"""Read-only drift cycle: baseline init, reported-once checks and approval."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from collectors.filesystem import take_snapshot
from core.drift_detection import (
    Change,
    PathSpec,
    compare_snapshots,
    describe_changes,
    flags_for,
)
from core.timeutil import utc_now
from engine.ingest import prepare_event
from storage.drift_repository import (
    accept_baseline as accept_baseline_repo,
)
from storage.drift_repository import (
    get_baseline_snapshot,
    get_previous_snapshot,
    list_monitored_paths,
    save_snapshot,
    seed_monitored_paths,
)
from storage.repositories import save_event, write_audit
from storage.severity_repository import seed_defaults

__all__ = ["DriftReport", "accept_baseline", "baseline_status_for", "check_drift", "init_drift"]


@dataclass
class DriftReport:
    baselines: int = 0
    snapshots: int = 0
    drift_events: int = 0
    warnings: list[str] = field(default_factory=list)


def accept_baseline(
    identifier: int, actor: str, reason: str, db_path: str | Path | None = None
) -> None:
    accept_baseline_repo(identifier, actor, reason, db_path)


def baseline_status_for(identifier: int, db_path: str | Path | None = None) -> str:
    """Return clean/drifted for one monitored path versus its approved baseline."""
    path = next((item for item in list_monitored_paths(db_path) if item.id == identifier), None)
    if path is None:
        raise ValueError(f"unknown monitored path: {identifier}")
    current = get_previous_snapshot(path.path, db_path)
    if current is None:
        return "drifted"
    return _baseline_status(path.as_spec(), current, db_path)


def init_drift(
    db_path: str | Path | None = None,
    now: datetime | None = None,
    *,
    force: bool = False,
    actor: str = "system",
) -> DriftReport:
    """Record baseline snapshots for enabled paths that have none yet."""
    reference = now or utc_now()
    seed_defaults(db_path)
    seed_monitored_paths(db_path)
    report = DriftReport()
    for path in list_monitored_paths(db_path, enabled_only=True):
        if get_previous_snapshot(path.path, db_path) is not None and not force:
            continue
        snapshot, warnings = take_snapshot(path.as_spec(), now=reference)
        save_snapshot(snapshot, is_baseline=True, db_path=db_path)
        write_audit(
            actor,
            "drift.baseline_init",
            target_type="monitored_path",
            target_id=str(path.id),
            after={"path": path.path, "force": force},
            db_path=db_path,
        )
        report.baselines += 1
        report.warnings.extend(warnings)
    return report


def _baseline_status(path: PathSpec, current: dict[str, Any], db_path: str | Path | None) -> str:
    baseline = get_baseline_snapshot(path.path, db_path)
    if baseline is None:
        return "drifted"
    return "clean" if not compare_snapshots(baseline, current, path) else "drifted"


def _event(
    path: PathSpec,
    changes: list[Change],
    flags: list[str],
    only_mtime: bool,
    baseline_status: str,
    warnings: list[str],
    now: datetime,
) -> dict[str, Any]:
    descriptions = describe_changes(changes, path, flags, only_mtime)
    return {
        "timestamp": now.isoformat(),
        "source": "filesystem",
        "event_type": "config_drift",
        "severity": "low",
        "description": " ".join(descriptions),
        "file_path": path.path,
        "details": {
            "path": path.path,
            "kind": path.kind,
            "sensitivity": path.sensitivity,
            "category": path.category,
            "changed_fields": [change.field for change in changes],
            "changes": [
                {"field": change.field, "old": change.old, "new": change.new} for change in changes
            ],
            "flags": flags,
            "only_mtime": only_mtime,
            "baseline_status": baseline_status,
            "warnings": warnings,
        },
    }


def check_drift(db_path: str | Path | None = None, now: datetime | None = None) -> DriftReport:
    """Compare each path with its previous snapshot and report changes exactly once."""
    reference = now or utc_now()
    seed_defaults(db_path)
    seed_monitored_paths(db_path)
    report = DriftReport()
    for path in list_monitored_paths(db_path, enabled_only=True):
        current, warnings = take_snapshot(path.as_spec(), now=reference)
        report.warnings.extend(warnings)
        previous = get_previous_snapshot(path.path, db_path)
        if previous is None:
            save_snapshot(current, is_baseline=True, db_path=db_path)
            report.baselines += 1
            continue
        changes = compare_snapshots(previous, current, path.as_spec())
        if changes:
            flags = flags_for(previous, current, changes)
            only_mtime = len(changes) == 1 and changes[0].field == "mtime"
            status = _baseline_status(path.as_spec(), current, db_path)
            event = _event(path.as_spec(), changes, flags, only_mtime, status, warnings, reference)
            prepared = prepare_event(event, db_path, reference)
            if prepared is not None:
                resolved, allowlisted = prepared
                save_event(resolved, db_path, allowlisted=allowlisted)
                report.drift_events += 1
        save_snapshot(current, db_path=db_path)
        report.snapshots += 1
    return report
