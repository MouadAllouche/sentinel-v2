"""Correlation cycle orchestration: components -> plan -> idempotent storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.correlation import CorrelationSettings, correlate
from core.incidents import plan_incidents
from core.timeutil import utc_now
from storage.incident_repository import apply_incidents, list_incidents
from storage.rules_repository import get_events_for_rules, list_findings

__all__ = ["CorrelationReport", "run_correlation"]


@dataclass
class CorrelationReport:
    components: int = 0
    incidents_created: int = 0
    incidents_extended: int = 0
    incidents_merged: int = 0


def run_correlation(
    db_path: str | Path | None = None, now: datetime | None = None
) -> CorrelationReport:
    reference = now or utc_now()
    events = get_events_for_rules("1970-01-01T00:00:00+00:00", db_path)
    list_findings({}, db_path=db_path)  # findings are represented by rule_triggered events
    findings = [
        {
            "rule_id": (event.get("details") or {}).get("rule_id"),
            "rule_name": (event.get("details") or {}).get("rule_name"),
            "tier_label": (event.get("details") or {}).get("tier_label"),
            "severity": event.get("severity"),
            "explanation": event.get("description"),
            "evidence_event_ids": (event.get("details") or {}).get("evidence_event_ids", []),
            "mitre": (event.get("details") or {}).get("mitre", []),
        }
        for event in events
        if event.get("event_type") == "rule_triggered"
    ]
    components = correlate(events, CorrelationSettings(), reference)
    existing: list[dict[str, Any]] = [dict(item) for item in list_incidents(db_path=db_path)]
    changes = plan_incidents(components, existing, reference, findings=findings)
    links = [link for component in components for link in component.links]
    apply_incidents(changes, db_path, events=events, links=links)
    report = CorrelationReport(components=len(components))
    for change in changes:
        if change.action == "create":
            report.incidents_created += 1
        elif change.action == "extend":
            report.incidents_extended += 1
        elif change.action == "merge":
            report.incidents_merged += 1
    return report
