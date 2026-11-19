"""Scoring cycle: assess incidents, persist reasons and propagate severity."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.risk_scoring import DEFAULT_THRESHOLDS, Decay, score_incident
from core.timeutil import utc_now
from storage.incident_repository import list_incidents
from storage.repositories import get_events_by_ids, get_setting, set_setting
from storage.risk_repository import apply_assessment
from storage.rules_repository import list_findings, list_rules

__all__ = ["ScoringReport", "run_scoring"]


@dataclass
class ScoringReport:
    assessments: int = 0
    severity_changes: int = 0


def _findings_for(
    incident: dict[str, Any], rows: list[dict[str, Any]], rule_names: dict[str, str]
) -> list[dict[str, Any]]:
    event_ids = set(incident.get("event_ids", []))
    result: list[dict[str, Any]] = []
    for row in rows:
        evidence = set(json.loads(row.get("evidence_event_ids_json") or "[]"))
        if not evidence & event_ids:
            continue
        rule_id = row["rule_id"]
        result.append(
            {
                "rule_id": rule_id,
                "rule_name": rule_names.get(rule_id, rule_id),
                "rule_version": row["rule_version"],
                "tier_index": row["tier_index"],
                "tier_label": f"tier {row['tier_index'] + 1}",
                "severity": row["severity"],
                "points": row["points"],
                "window_end": row["window_end"],
                "evidence_event_ids": sorted(evidence),
                "explanation": f"Rule {rule_id} matched with {row['observed']} observations",
            }
        )
    return result


def run_scoring(db_path: str | Path | None = None, now: datetime | None = None) -> ScoringReport:
    reference = now or utc_now()
    report = ScoringReport()
    thresholds = get_setting("risk.severity_thresholds", db_path) or dict(DEFAULT_THRESHOLDS)
    config = get_setting("risk.recency_decay", db_path) or {"enabled": False, "half_life_hours": 72}
    set_setting("risk.severity_thresholds", thresholds, updated_by="system", db_path=db_path)
    set_setting("risk.recency_decay", config, updated_by="system", db_path=db_path)
    rules = list_rules(db_path=db_path)
    rule_names = {rule.id: rule.name for rule in rules}
    meta_rules = [rule for rule in rules if rule.kind == "incident_meta" and rule.enabled]
    finding_rows = list_findings({}, db_path=db_path, limit=None)

    for incident in list_incidents(db_path=db_path):
        events = list(get_events_by_ids(incident.get("event_ids", []), db_path).values())
        findings = _findings_for(incident, finding_rows, rule_names)
        assessment = score_incident(
            incident,
            events,
            findings,
            meta_rules,
            thresholds,
            reference,
            decay=Decay(
                enabled=bool(config.get("enabled")),
                half_life_hours=int(config.get("half_life_hours", 72)),
            ),
            rule_names=rule_names,
        )
        previous = str(incident.get("severity", "low"))
        changed = assessment.severity != previous
        apply_assessment(
            "incident",
            int(incident["id"]),
            assessment,
            incident_update={
                "score": assessment.score,
                "severity": assessment.severity,
                "computed_at": reference.isoformat(),
            },
            severity_change=(previous, assessment.severity) if changed else None,
            db_path=db_path,
        )
        report.assessments += 1
        if changed:
            report.severity_changes += 1
    return report
