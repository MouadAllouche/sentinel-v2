"""Pure single-event field-match evaluator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from core.conditions import evaluate as evaluate_condition
from core.conditions import validate_condition
from core.rules.models import Rule
from core.rules.threshold import Finding

__all__ = ["evaluate_field_match"]


def _parse(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def evaluate_field_match(rule: Rule, events: list[dict[str, Any]], now: datetime) -> list[Finding]:
    """One finding per matching event, with optional per-group cooldown collapse."""
    del now
    condition = (
        validate_condition(rule.match.conditions) if rule.match.conditions is not None else None
    )
    findings: list[Finding] = []
    last_by_group: dict[str, datetime] = {}
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
        if rule.scope.exclude_allowlisted and (
            (event.get("enrichment") or {}).get("allowlist_suppressed") is True
        ):
            continue
        if condition is not None and not evaluate_condition(condition, event):
            continue
        stamp = _parse(event["timestamp"])
        entity = "&".join(f"{field}={event[field]}" for field in rule.group_by) or "global"
        previous = last_by_group.get(entity)
        if (
            previous is not None
            and rule.cooldown_seconds > 0
            and stamp - previous <= timedelta(seconds=rule.cooldown_seconds)
        ):
            continue
        last_by_group[entity] = stamp
        timestamp = stamp.isoformat()
        identifier = int(event.get("id", 0))
        findings.append(
            Finding(
                rule_id=rule.id,
                rule_version=rule.version,
                group_key=f"event={identifier}",
                tier_index=0,
                tier_label=rule.name,
                severity=rule.severity,
                points=rule.points,
                window_start=timestamp,
                window_end=timestamp,
                observed=1,
                threshold=1,
                window_seconds=0,
                evidence_event_ids=[identifier],
                explanation=(
                    f"Suspicious {event['event_type']} matched by rule '{rule.name}' for {entity}; "
                    "this is a rule match, not proof of malicious activity."
                ),
            )
        )
    findings.sort(key=lambda finding: (finding.window_start, finding.group_key))
    return findings
