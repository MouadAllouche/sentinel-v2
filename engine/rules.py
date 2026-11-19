"""Rule cycle orchestration: evaluate, persist findings, emit deterministic events."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.normalizer import normalize_event
from core.rules.engine import evaluate_rules
from core.rules.threshold import Finding
from core.timeutil import utc_now
from storage.repositories import save_event
from storage.rules_repository import (
    get_events_for_rules,
    list_rules,
    save_findings,
)

logger = logging.getLogger(__name__)


@dataclass
class RulesReport:
    rules_evaluated: int = 0
    findings_new: int = 0
    triggered_events_new: int = 0
    warnings: list[str] = field(default_factory=list)


def _triggered_event(rule: Any, finding: Finding) -> dict[str, Any]:
    details = {
        "rule_id": finding.rule_id,
        "rule_version": finding.rule_version,
        "tier_label": finding.tier_label,
        "group_key": finding.group_key,
        "observed": finding.observed,
        "threshold": finding.threshold,
        "window_seconds": finding.window_seconds,
        "evidence_event_ids": finding.evidence_event_ids,
        "mitre": rule.mitre,
        "points": finding.points,
    }
    return normalize_event(
        {
            "timestamp": finding.window_end,
            "source": "rules",
            "event_type": "rule_triggered",
            "severity": finding.severity,
            "severity_source": f"rule:{finding.rule_id}",
            "description": finding.explanation,
            "details": details,
        }
    )


def run_rules(db_path: str | Path | None = None, now: datetime | None = None) -> RulesReport:
    """Run all enabled rules once; re-runs are idempotent by finding/event hash."""
    reference = now or utc_now()
    report = RulesReport()
    rules = [rule for rule in list_rules(db_path=db_path) if rule.enabled]
    report.rules_evaluated = len(rules)
    if not rules:
        return report

    longest = max(
        (tier.window_seconds for rule in rules for tier in rule.tiers),
        default=60,
    ) + max((rule.cooldown_seconds for rule in rules), default=0)
    since = (reference - timedelta(seconds=longest)).isoformat()
    events = get_events_for_rules(since, db_path)
    findings, warnings = evaluate_rules(rules, events, reference)
    report.warnings.extend(warnings)

    saved = save_findings(findings, db_path)
    for finding, (identifier, is_new) in zip(findings, saved, strict=True):
        del identifier
        if not is_new:
            continue
        rule = next(rule for rule in rules if rule.id == finding.rule_id)
        event = _triggered_event(rule, finding)
        if save_event(event, db_path, severity_source=f"rule:{finding.rule_id}") is not None:
            report.triggered_events_new += 1
        report.findings_new += 1
    for warning in warnings:
        logger.warning("rules: %s", warning)
    return report
