"""Pure retention planning. No DB, clock or filesystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = ["DEFAULT_POLICY", "PrunePlan", "plan_prune", "validate_policy"]

DEFAULT_POLICY: dict[str, Any] = {
    "events": {
        "low_days": 14,
        "medium_days": 60,
        "high_days": 365,
        "critical_days": 365,
    },
    "findings_days": 365,
    "snapshots_keep_per_path": 200,
    "collector_runs_days": 30,
    "cycle_runs_days": 14,
    "notification_log_days": 90,
    "audit_days": 730,
    "sessions_expired_days": 7,
    "vacuum": True,
}


@dataclass
class PrunePlan:
    delete_counts: dict[str, int] = field(default_factory=dict)
    keep_baselines: bool = True
    vacuum: bool = False


def validate_policy(policy: dict[str, Any]) -> None:
    for key, value in policy["events"].items():
        if not isinstance(value, int) or value < 1:
            raise ValueError(f"events.{key} must be a positive integer")
    for key in (
        "findings_days",
        "snapshots_keep_per_path",
        "collector_runs_days",
        "cycle_runs_days",
        "notification_log_days",
        "audit_days",
        "sessions_expired_days",
    ):
        if not isinstance(policy.get(key), int) or policy[key] < 1:
            raise ValueError(f"{key} must be a positive integer")


def plan_prune(policy: dict[str, Any], stats: dict[str, Any], now: datetime) -> PrunePlan:
    """Plan deletions without ever touching evidence linked to open incidents."""
    del now
    validate_policy(policy)
    events = stats.get("events", {})
    protected = int(events.get("linked_open", 0))
    counts: dict[str, int] = {}
    for severity in ("low", "medium", "high", "critical"):
        total = int(events.get(severity, 0))
        old = events.get(f"{severity}_old")
        eligible = max(0, total - protected)
        counts[f"events_{severity}"] = min(int(old), eligible) if old is not None else eligible
    for table in ("findings", "collector_runs", "cycle_runs", "notification_log", "audit"):
        counts[table] = int(stats.get(table, 0))
    return PrunePlan(
        delete_counts=counts,
        keep_baselines=True,
        vacuum=bool(policy.get("vacuum", False)),
    )
