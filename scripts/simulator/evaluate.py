"""Outcome evaluation and aggregation for the threat simulator (Phase 20)."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from scripts.simulator.runner import ScenarioResult
from scripts.simulator.scenarios import get_scenario

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _severity(value: Any) -> str:
    return str(value or "low").lower()


def _highest(*values: str) -> str:
    return max(values, key=lambda item: SEVERITY_ORDER.get(item, 0), default="low")


def _rule_id(item: dict[str, Any]) -> str:
    if item.get("rule_id"):
        return str(item["rule_id"])
    source = str(item.get("severity_source") or "")
    return source.split(":", 1)[1] if source.startswith("rule:") else ""


@dataclass
class Evaluation:
    scenario_id: str
    category: str
    detected: bool
    matched_rules: list[str]
    highest_severity: str
    incident_id: int | None
    score: int
    time_to_detect: float | None
    false_positives: int
    outcome: str
    note: str


def evaluate(result: ScenarioResult) -> Evaluation:
    scenario = get_scenario(result.scenario_id)
    expectation = scenario.expectation
    matched = sorted(
        {
            identifier
            for identifier in (
                _rule_id(item) for item in list(result.findings) + list(result.anomalies)
            )
            if identifier
        }
    )
    severities = [
        _severity(item.get("severity"))
        for item in list(result.findings) + list(result.anomalies) + list(result.incidents)
    ]
    highest = _highest(*severities) if severities else "low"
    incident = max(
        result.incidents,
        key=lambda item: SEVERITY_ORDER.get(_severity(item.get("severity")), 0),
        default=None,
    )
    incident_id = int(incident["id"]) if incident else None
    score = int(max((int(item.get("score") or 0) for item in result.incidents), default=0))

    allowed = SEVERITY_ORDER.get(expectation.max_false_positive_severity, 0)
    false_positives = sum(
        1
        for item in list(result.findings) + list(result.incidents)
        if SEVERITY_ORDER.get(_severity(item.get("severity")), 0) > allowed
    )
    if scenario.category == "benign":
        detected = bool(false_positives)
    elif scenario.category == "evasion":
        detected = bool(matched or result.incidents)
    else:
        detected = bool(set(matched) & set(expectation.rules_any_of)) or bool(
            result.incidents
            and SEVERITY_ORDER.get(highest, 0) >= SEVERITY_ORDER.get(expectation.min_severity, 0)
        )

    if scenario.category == "attack":
        outcome = "TRUE_POSITIVE" if detected else "FALSE_NEGATIVE"
    elif scenario.category == "benign":
        outcome = "FALSE_POSITIVE" if detected else "TRUE_NEGATIVE"
    elif scenario.category == "evasion":
        outcome = "UNEXPECTED_DETECTION" if detected else "KNOWN_BLIND_SPOT"
    else:
        outcome = "TRUE_POSITIVE" if detected else "FALSE_NEGATIVE"

    ttd: float | None = None
    if detected and result.first_malicious_at is not None:
        moments: list[float] = []
        for item in list(result.findings) + list(result.anomalies):
            # Time-to-detect is measured from the first finding matching the
            # scenario's expectation, not from an unrelated earlier finding.
            if expectation.rules_any_of and _rule_id(item) not in expectation.rules_any_of:
                continue
            value = item.get("window_end") or item.get("timestamp")
            if not value:
                continue
            try:
                moment = datetime.fromisoformat(str(value))
            except ValueError:
                continue
            moments.append((moment - result.first_malicious_at).total_seconds())
        if moments:
            ttd = max(0.0, min(moments))

    return Evaluation(
        scenario_id=result.scenario_id,
        category=scenario.category,
        detected=detected,
        matched_rules=matched,
        highest_severity=highest,
        incident_id=incident_id,
        score=score,
        time_to_detect=ttd,
        false_positives=false_positives,
        outcome=outcome,
        note=expectation.note,
    )


def aggregate(evaluations: list[Evaluation]) -> dict[str, Any]:
    attacks = [item for item in evaluations if item.category == "attack"]
    benign = [item for item in evaluations if item.category == "benign"]
    detected_attacks = sum(1 for item in attacks if item.detected)
    times = [item.time_to_detect for item in evaluations if item.time_to_detect is not None]
    distribution: dict[str, int] = {}
    for item in evaluations:
        distribution[item.highest_severity] = distribution.get(item.highest_severity, 0) + 1
    coverage: dict[str, dict[str, int]] = {}
    for item in evaluations:
        scenario = get_scenario(item.scenario_id)
        for technique in scenario.mitre:
            row = coverage.setdefault(technique, {"scenarios": 0, "detected": 0})
            row["scenarios"] += 1
            row["detected"] += int(item.detected)
    return {
        "scenarios": len(evaluations),
        "detected": sum(1 for item in evaluations if item.detected),
        "not_detected": sum(1 for item in evaluations if not item.detected),
        "detection_rate": detected_attacks / len(attacks) if attacks else 0.0,
        "false_positive_count": sum(item.false_positives for item in benign),
        "median_time_to_detect": statistics.median(times) if times else None,
        "severity_distribution": dict(sorted(distribution.items())),
        "mitre_coverage": dict(sorted(coverage.items())),
        "outcomes": {
            name: sum(1 for item in evaluations if item.outcome == name)
            for name in (
                "TRUE_POSITIVE",
                "FALSE_NEGATIVE",
                "TRUE_NEGATIVE",
                "FALSE_POSITIVE",
                "KNOWN_BLIND_SPOT",
                "UNEXPECTED_DETECTION",
            )
        },
    }
