"""Pure, explainable risk scoring. No DB, clock, network or ML."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.events import SEVERITY_ORDER
from core.rules.models import Rule

__all__ = [
    "DEFAULT_THRESHOLDS",
    "Decay",
    "RiskAssessment",
    "event_score",
    "score_incident",
    "score_severity",
    "validate_thresholds",
]

DEFAULT_THRESHOLDS: dict[str, int] = {"medium": 20, "high": 40, "critical": 70}
_PRIVILEGED = frozenset({"sudo_command", "su_command", "user_created", "group_member_added"})
_PERSISTENCE = frozenset({"config_drift", "user_created", "group_member_added"})
_META_OPS = {"gte", "lte", "eq", "ne", "gt", "lt"}


@dataclass(frozen=True)
class Decay:
    enabled: bool = False
    half_life_hours: int = 72


@dataclass
class RiskAssessment:
    target_type: str
    target_id: int
    score: float
    raw_score: float
    capped: bool
    severity: str
    reasons: list[dict[str, Any]] = field(default_factory=list)
    computed_at: str = ""


def validate_thresholds(thresholds: dict[str, int]) -> None:
    raw = [thresholds.get(key) for key in ("medium", "high", "critical")]
    if any(value is None for value in raw):
        raise ValueError("thresholds must define medium, high and critical")
    values = [int(value) for value in raw if value is not None]
    if any(not 1 <= value <= 100 for value in values):
        raise ValueError("severity thresholds must be between 1 and 100")
    if values != sorted(set(values)) or len(set(values)) != 3:
        raise ValueError("severity thresholds must be strictly increasing")


def score_severity(score: float, thresholds: dict[str, int]) -> str:
    validate_thresholds(thresholds)
    if score >= thresholds["critical"]:
        return "critical"
    if score >= thresholds["high"]:
        return "high"
    if score >= thresholds["medium"]:
        return "medium"
    return "low"


def event_score(event: dict[str, Any]) -> dict[str, Any]:
    """Informational score for one event; never added to incident scores."""
    from core.severity import DEFAULT_TYPE_DEFAULTS

    entry = DEFAULT_TYPE_DEFAULTS.get(str(event.get("event_type")))
    points = entry.points if entry else 0
    return {
        "source": "event_type_default",
        "points": points,
        "explanation": f"Event type {event.get('event_type')} has default weight {points}",
    }


def _parse(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _compare(left: Any, op: str, right: Any) -> bool:
    if op not in _META_OPS:
        return False
    if isinstance(right, bool) or isinstance(left, bool):
        left_bool = bool(left)
        right_bool = bool(right)
        return {
            "eq": left_bool == right_bool,
            "ne": left_bool != right_bool,
        }.get(op, False)
    try:
        result: bool = {
            "gte": left >= right,
            "lte": left <= right,
            "eq": left == right,
            "ne": left != right,
            "gt": left > right,
            "lt": left < right,
        }[op]
        return result
    except (TypeError, KeyError):
        return False


def _metrics(
    incident: dict[str, Any], events: list[dict[str, Any]], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    types = {str(event.get("event_type")) for event in events}
    return {
        "distinct_event_types": len(types),
        "distinct_rules_fired": len({str(finding.get("rule_id")) for finding in findings}),
        "event_count": len(events) or len(incident.get("event_ids", [])),
        "has_strong_links_only": float(incident.get("weak_link_ratio", 0)) <= 0.0,
        "span_minutes": max(
            0.0,
            (_parse(incident["last_seen"]) - _parse(incident["first_seen"])).total_seconds() / 60,
        )
        if incident.get("first_seen") and incident.get("last_seen")
        else 0.0,
        "weak_link_ratio": float(incident.get("weak_link_ratio", 0)),
        "contains_privileged_activity": bool(types & _PRIVILEGED),
        "contains_persistence_change": bool(types & _PERSISTENCE),
        "types": types,
    }


def _meta_condition_holds(condition: dict[str, Any], metrics: dict[str, Any]) -> bool:
    metric = str(condition.get("metric", ""))
    if metric.startswith("has_event_type:"):
        value = metric.split(":", 1)[1] in metrics["types"]
    elif metric in metrics:
        value = metrics[metric]
    else:
        return False
    return _compare(value, str(condition.get("op")), condition.get("value"))


def _highest_per_rule(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for finding in findings:
        rule_id = str(finding.get("rule_id", "unknown"))
        current = best.get(rule_id)
        rank = (
            SEVERITY_ORDER.get(str(finding.get("severity", "low")), 0),
            int(finding.get("points", 0)),
        )
        current_rank = (
            (
                SEVERITY_ORDER.get(str(current.get("severity", "low")), 0),
                int(current.get("points", 0)),
            )
            if current
            else (-1, -1)
        )
        if rank > current_rank:
            best[rule_id] = finding
    return [best[key] for key in sorted(best)]


def score_incident(
    incident: dict[str, Any],
    events: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    meta_rules: list[Rule],
    thresholds: dict[str, int],
    now: datetime,
    decay: Decay | None = None,
    rule_names: dict[str, str] | None = None,
) -> RiskAssessment:
    """Score one incident from distinct rule findings plus incident-meta rules."""
    validate_thresholds(thresholds)
    policy = decay or Decay()
    selected = _highest_per_rule(findings)
    metrics = _metrics(incident, events, findings)
    reasons: list[dict[str, Any]] = []
    raw = 0.0
    rule_floor = "low"
    floor_detail = ""
    all_old = bool(selected)

    for finding in selected:
        points = float(finding.get("points", 0))
        reason: dict[str, Any] = {
            "kind": "rule",
            "rule_id": finding.get("rule_id"),
            "rule_name": (rule_names or {}).get(
                str(finding.get("rule_id")), finding.get("rule_name", finding.get("rule_id"))
            ),
            "tier_label": finding.get("tier_label"),
            "severity": finding.get("severity"),
            "points": points,
            "explanation": finding.get("explanation", ""),
            "evidence_event_ids": finding.get("evidence_event_ids", []),
        }
        severity = str(finding.get("severity", "low"))
        if SEVERITY_ORDER.get(severity, 0) > SEVERITY_ORDER.get(rule_floor, 0):
            rule_floor = severity
            floor_detail = f"rule '{finding.get('rule_id')}' tier '{finding.get('tier_label')}'"
        if policy.enabled:
            try:
                age_hours = max(0.0, (now - _parse(finding["window_end"])).total_seconds() / 3600)
            except (KeyError, ValueError):
                age_hours = 0.0
            if age_hours <= policy.half_life_hours * 7:
                all_old = False
            factor = 0.5 ** (age_hours / max(1, policy.half_life_hours))
            reason["original_points"] = points
            points = round(points * factor, 4)
            reason["points"] = points
        else:
            all_old = False
        raw += points
        reasons.append(reason)

    for rule in meta_rules:
        conditions = rule.meta_conditions
        if (
            not conditions
            or len(conditions) > 5
            or not all(_meta_condition_holds(dict(item), metrics) for item in conditions)
        ):
            continue
        reasons.append(
            {
                "kind": "meta",
                "rule_id": rule.id,
                "rule_name": rule.name,
                "tier_label": "meta",
                "severity": rule.severity,
                "points": rule.points,
                "explanation": f"Incident meta rule '{rule.name}' matched the incident aggregate",
                "evidence_event_ids": [],
            }
        )
        raw += rule.points

    score = min(100.0, raw)
    band = score_severity(score, thresholds)
    severity = band if SEVERITY_ORDER[band] >= SEVERITY_ORDER[rule_floor] else rule_floor
    basis = (
        "rule floor"
        if severity == rule_floor and SEVERITY_ORDER[rule_floor] > SEVERITY_ORDER[band]
        else "score band"
    )
    if policy.enabled and all_old:
        if incident.get("status") == "open" and rule_floor != "low":
            severity = rule_floor
            basis = "rule floor on an open incident despite old findings"
        else:
            severity = "low" if rule_floor != "critical" else "medium"
            basis = "recency floor (findings older than 7 half-lives)"
    reasons.append(
        {
            "kind": "summary",
            "points": 0,
            "raw_score": raw,
            "score": score,
            "capped": raw > 100,
            "severity": severity,
            "severity_basis": basis,
            "explanation": (
                f"Severity {severity} from {basis}"
                + (f" ({floor_detail})" if "floor" in basis and floor_detail else "")
            ),
        }
    )
    if metrics["weak_link_ratio"] > 0.5:
        reasons.append(
            {
                "kind": "caveat",
                "points": 0,
                "explanation": (
                    "Many links are time-proximity only; treat the grouping with caution"
                ),
            }
        )
    return RiskAssessment(
        target_type="incident",
        target_id=int(incident.get("id", 0)),
        score=score,
        raw_score=raw,
        capped=raw > 100,
        severity=severity,
        reasons=reasons,
        computed_at=now.isoformat(),
    )
