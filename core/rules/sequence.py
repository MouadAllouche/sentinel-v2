"""Pure sequence evaluator: A then B (then C) for the same entity."""

from __future__ import annotations

from bisect import bisect_right
from datetime import UTC, datetime, timedelta
from typing import Any

from core.conditions import evaluate as evaluate_condition
from core.conditions import validate_condition
from core.rules.models import Rule
from core.rules.threshold import Finding

__all__ = ["evaluate_sequence"]


def _parse(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _usable(event: Any) -> bool:
    if not isinstance(event, dict) or "timestamp" not in event or "event_type" not in event:
        return False
    try:
        _parse(event["timestamp"])
    except (TypeError, ValueError):
        return False
    return True


def _matches(step: dict[str, Any], event: dict[str, Any], condition: Any) -> bool:
    types = (step.get("match") or {}).get("event_types") or []
    if event.get("event_type") not in types:
        return False
    return condition is None or evaluate_condition(condition, event)


def _step_condition(step: dict[str, Any]) -> Any:
    condition = (step.get("match") or {}).get("conditions")
    return validate_condition(condition) if condition is not None else None


def _first_satisfaction(
    step: dict[str, Any], group: list[dict[str, Any]], condition: Any
) -> datetime | None:
    matching = [event for event in group if _matches(step, event, condition)]
    times = [_parse(event["timestamp"]) for event in matching]
    required = int(step.get("min_count", 1))
    window = step.get("window_seconds")
    for index, moment in enumerate(times):
        start = moment - timedelta(seconds=window) if window else datetime.min.replace(tzinfo=UTC)
        left = bisect_right(times, start)
        if index - left + 1 >= required:
            return moment
    return None


def evaluate_sequence(rule: Rule, events: list[dict[str, Any]], now: datetime) -> list[Finding]:
    """Return every completed sequence per entity; cooldown separates episodes."""
    del now
    groups: dict[str, list[dict[str, Any]]] = {}
    for event in sorted(
        (item for item in events if _usable(item)),
        key=lambda item: (_parse(item["timestamp"]), int(item.get("id", 0) or 0)),
    ):
        if any(event.get(field) in (None, "") for field in rule.correlate_on):
            continue
        key = "&".join(f"{field}={event[field]}" for field in rule.correlate_on)
        groups.setdefault(key, []).append(event)

    findings: list[Finding] = []
    for key, group in groups.items():
        cursor = datetime.min.replace(tzinfo=UTC)
        while True:
            eligible = [event for event in group if _parse(event["timestamp"]) > cursor]
            if not eligible:
                break
            moments: list[datetime] = []
            previous: datetime | None = None
            for step in rule.steps:
                condition = _step_condition(step)
                candidates = [
                    event
                    for event in eligible
                    if previous is None or _parse(event["timestamp"]) > previous
                ]
                moment = _first_satisfaction(step, candidates, condition)
                if moment is None:
                    break
                if previous is not None and moment - moments[0] > timedelta(
                    seconds=rule.within_seconds
                ):
                    break
                moments.append(moment)
                previous = moment
            if len(moments) != len(rule.steps):
                break
            final = moments[-1]
            evidence: list[int] = []
            first_evidence: datetime | None = None
            group_start = _parse(eligible[0]["timestamp"]) - timedelta(seconds=1)
            for index, step in enumerate(rule.steps):
                lower = moments[index - 1] if index > 0 else group_start
                upper = moments[index + 1] if index + 1 < len(moments) else final
                window = step.get("window_seconds")
                condition = _step_condition(step)
                for event in eligible:
                    stamp = _parse(event["timestamp"])
                    if stamp <= lower or stamp > upper:
                        continue
                    if window and stamp < moments[index] - timedelta(seconds=window):
                        continue
                    identifier = int(event.get("id", 0) or 0)
                    if _matches(step, event, condition) and identifier not in evidence:
                        evidence.append(identifier)
                        if first_evidence is None or stamp < first_evidence:
                            first_evidence = stamp
            start = (first_evidence or moments[0]).isoformat()
            findings.append(
                Finding(
                    rule_id=rule.id,
                    rule_version=rule.version,
                    group_key=key,
                    tier_index=0,
                    tier_label=rule.name,
                    severity=rule.severity,
                    points=rule.points,
                    window_start=start,
                    window_end=final.isoformat(),
                    observed=len(evidence),
                    threshold=len(rule.steps),
                    window_seconds=rule.within_seconds,
                    evidence_event_ids=sorted(evidence),
                    explanation=(
                        f"Possible sequence for {key}: {len(rule.steps)} steps completed from "
                        f"{(first_evidence or moments[0]).strftime('%H:%M:%S')} to "
                        f"{final.strftime('%H:%M:%S')}; "
                        "shared attributes and order only, not proof of a single actor."
                    ),
                )
            )
            cursor = final + timedelta(seconds=rule.cooldown_seconds)
    findings.sort(key=lambda finding: (finding.group_key, finding.window_start))
    return findings
