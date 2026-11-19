"""Pure new-value detection: first value seen for an entity after a learning period."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from core.conditions import evaluate as evaluate_condition
from core.conditions import validate_condition
from core.rules.models import Rule
from core.rules.threshold import Finding

__all__ = ["ValueHistory", "evaluate_new_value"]


@dataclass
class ValueHistory:
    """Pre-aggregated history supplied by the storage layer."""

    values: set[str] = field(default_factory=set)
    count: int = 0


def _parse(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _value(event: dict[str, Any], name: str) -> Any:
    if name.startswith("details."):
        details = event.get("details") or {}
        return details.get(name.split(".", 1)[1]) if isinstance(details, dict) else None
    return event.get(name)


def evaluate_new_value(
    rule: Rule,
    events: list[dict[str, Any]],
    history: dict[str, ValueHistory],
    now: datetime,
) -> list[Finding]:
    """Fire when a value has not been seen for its entity in the learning window."""
    condition = (
        validate_condition(rule.match.conditions) if rule.match.conditions is not None else None
    )
    findings: list[Finding] = []
    seen_in_batch: dict[str, set[str]] = {}
    usable = []
    for event in events:
        if not isinstance(event, dict) or "timestamp" not in event or "event_type" not in event:
            continue
        try:
            _parse(event["timestamp"])
        except (TypeError, ValueError):
            continue
        usable.append(event)
    for event in sorted(
        usable, key=lambda item: (_parse(item["timestamp"]), int(item.get("id", 0)))
    ):
        if event.get("event_type") not in rule.match.event_types:
            continue
        if condition is not None and not evaluate_condition(condition, event):
            continue
        stamp = _parse(event["timestamp"])
        if now - stamp > timedelta(days=rule.learning_days):
            continue
        entity = event.get(rule.per or "")
        value = _value(event, rule.field or "")
        if entity in (None, "") or value in (None, ""):
            continue
        entity_key = str(entity)
        prior = history.get(entity_key, ValueHistory())
        if prior.count < rule.min_history_events:
            continue
        known = prior.values | seen_in_batch.get(entity_key, set())
        if str(value) in known:
            continue
        seen_in_batch.setdefault(entity_key, set()).add(str(value))
        timestamp = stamp.isoformat()
        findings.append(
            Finding(
                rule_id=rule.id,
                rule_version=rule.version,
                group_key=f"{rule.per}={entity_key}",
                tier_index=0,
                tier_label=rule.name,
                severity=rule.severity,
                points=rule.points,
                window_start=timestamp,
                window_end=timestamp,
                observed=1,
                threshold=rule.min_history_events,
                window_seconds=rule.learning_days * 86400,
                evidence_event_ids=[int(event.get("id", 0))],
                explanation=(
                    f"Possible first occurrence of {rule.field}={value} "
                    f"for {rule.per}={entity_key}; "
                    "the value was not seen in the learning window."
                ),
            )
        )
    return findings
