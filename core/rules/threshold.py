"""Pure sliding/fixed threshold evaluation with tiers, cooldown and escalation."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from core.conditions import evaluate as evaluate_condition
from core.conditions import validate_condition
from core.events import SEVERITY_ORDER
from core.rules.models import Rule

__all__ = ["Finding", "evaluate_threshold"]

EVIDENCE_CAP = 500
_ALIGNMENT_SECONDS = {"minute": 60, "hour": 3600, "day": 86400}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    rule_version: int
    group_key: str
    tier_index: int
    tier_label: str
    severity: str
    points: int
    window_start: str
    window_end: str
    observed: int
    threshold: int
    window_seconds: int
    evidence_event_ids: list[int]
    explanation: str

    @property
    def key(self) -> tuple[str, str, int, str]:
        """Deterministic identity: (rule_id, group_key, tier_index, window_start)."""
        return (self.rule_id, self.group_key, self.tier_index, self.window_start)


def _parse(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _human(seconds: int) -> str:
    if seconds and seconds % 3600 == 0:
        count = seconds // 3600
        return f"{count} hour" + ("s" if count != 1 else "")
    if seconds and seconds % 60 == 0:
        count = seconds // 60
        return f"{count} minute" + ("s" if count != 1 else "")
    return f"{seconds}s"


def _short(seconds: int) -> str:
    if seconds and seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds and seconds % 60 == 0:
        return f"{seconds // 60}min"
    return f"{seconds}s"


def _suppressed(event: dict[str, Any]) -> bool:
    enrichment = event.get("enrichment") or {}
    return isinstance(enrichment, dict) and enrichment.get("allowlist_suppressed") is True


def _filter_events(rule: Rule, events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    condition = validate_condition(rule.match.conditions) if rule.match.conditions else None
    allowed = set(rule.match.event_types)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("event_type") not in allowed:
            continue
        if rule.scope.exclude_allowlisted and _suppressed(event):
            continue
        if condition is not None and not evaluate_condition(condition, event):
            continue
        if any(event.get(field) in (None, "") for field in rule.group_by):
            continue
        key = "&".join(f"{field}={event[field]}" for field in rule.group_by) or "global"
        buckets.setdefault(key, []).append(event)
    for bucket in buckets.values():
        bucket.sort(key=lambda item: (_parse(item["timestamp"]), int(item.get("id", 0))))
    return buckets


def _count(window: list[dict[str, Any]], rule: Rule) -> int:
    if rule.aggregate.type != "distinct_count" or not rule.aggregate.field:
        return len(window)
    field = rule.aggregate.field
    values = set()
    for event in window:
        if field.startswith("details."):
            details = event.get("details") or {}
            value = str(details.get(field.split(".", 1)[1])) if isinstance(details, dict) else None
        else:
            value = event.get(field)
        if value is not None:
            values.add(str(value))
    return len(values)


@dataclass(frozen=True)
class _Satisfaction:
    tier_index: int
    tier: Any
    window_start: datetime
    window_end: datetime
    observed: int
    evidence: list[int]


def _sliding_satisfactions(
    tier_index: int, tier: Any, rule: Rule, group: list[dict[str, Any]]
) -> list[_Satisfaction]:
    times = [_parse(event["timestamp"]) for event in group]
    window = timedelta(seconds=tier.window_seconds)
    cooldown = rule.cooldown_seconds
    result: list[_Satisfaction] = []
    last_end: datetime | None = None
    for index, end in enumerate(times):
        start = end - window
        if last_end is not None:
            gap = (end - last_end).total_seconds()
            if not (start > last_end or (cooldown > 0 and gap >= cooldown)):
                continue
        left = bisect_right(times, start)
        candidate = group[left : index + 1]
        observed = _count(candidate, rule)
        if observed < tier.count:
            continue
        evidence = [int(event.get("id", 0)) for event in candidate[:EVIDENCE_CAP]]
        result.append(
            _Satisfaction(tier_index, tier, max(start, times[left]), end, observed, evidence)
        )
        last_end = end
    return result


def _fixed_satisfactions(
    tier_index: int, tier: Any, rule: Rule, group: list[dict[str, Any]]
) -> list[_Satisfaction]:
    length = _ALIGNMENT_SECONDS[rule.fixed_alignment or "minute"]
    buckets: dict[datetime, list[dict[str, Any]]] = {}
    for event in group:
        stamp = _parse(event["timestamp"])
        start = datetime(stamp.year, stamp.month, stamp.day, stamp.hour, stamp.minute, tzinfo=UTC)
        if length == 3600:
            start = start.replace(minute=0)
        elif length == 86400:
            start = start.replace(hour=0, minute=0)
        buckets.setdefault(start, []).append(event)
    result: list[_Satisfaction] = []
    last_start: datetime | None = None
    for start in sorted(buckets):
        if last_start is not None and start <= last_start + timedelta(
            seconds=rule.cooldown_seconds
        ):
            continue
        candidate = buckets[start]
        observed = _count(candidate, rule)
        if observed < tier.count:
            continue
        result.append(
            _Satisfaction(
                tier_index,
                tier,
                start,
                start + timedelta(seconds=tier.window_seconds),
                observed,
                [int(event.get("id", 0)) for event in candidate[:EVIDENCE_CAP]],
            )
        )
        last_start = start
    return result


def _explain(rule: Rule, group_key: str, item: _Satisfaction) -> str:
    event_types = "/".join(rule.match.event_types)
    if rule.aggregate.type == "distinct_count" and rule.aggregate.field:
        counted = f"{item.observed} distinct {rule.aggregate.field}s"
    else:
        counted = f"{item.observed} {event_types} events"
    return (
        f"{counted} from {group_key} within {_human(item.tier.window_seconds)} "
        f"(threshold: ≥{item.tier.count} in {_short(item.tier.window_seconds)} "
        f"→ {item.tier.severity}). "
        f"First at {item.window_start.strftime('%H:%M:%S')}, "
        f"last at {item.window_end.strftime('%H:%M:%S')}."
    )


def evaluate_threshold(
    rule: Rule,
    events: list[dict[str, Any]],
    now: datetime,
    should_stop: Callable[[], bool] | None = None,
) -> list[Finding]:
    """Return all findings for a threshold rule; output is order-independent."""
    del now  # the window semantics are defined entirely by event timestamps.
    buckets = _filter_events(rule, events)
    findings: list[Finding] = []
    for group_key, group in buckets.items():
        if should_stop is not None and should_stop():
            break
        satisfactions: list[_Satisfaction] = []
        for index, tier in enumerate(rule.tiers):
            satisfactions.extend(
                _sliding_satisfactions(index, tier, rule, group)
                if rule.window_mode == "sliding"
                else _fixed_satisfactions(index, tier, rule, group)
            )
        # Same window_end: only the highest tier (severity then points) survives.
        best_by_end: dict[datetime, _Satisfaction] = {}
        for item in satisfactions:
            current = best_by_end.get(item.window_end)
            rank = (SEVERITY_ORDER[item.tier.severity], item.tier.points)
            current_rank = (
                (SEVERITY_ORDER[current.tier.severity], current.tier.points)
                if current is not None
                else (-1, -1)
            )
            if rank > current_rank:
                best_by_end[item.window_end] = item
        ordered = sorted(best_by_end.values(), key=lambda item: item.window_end)
        current_rank = (-1, -1)
        last_time: datetime | None = None
        for item in ordered:
            rank = (SEVERITY_ORDER[item.tier.severity], item.tier.points)
            if (
                last_time is not None
                and (item.window_end - last_time).total_seconds() > rule.cooldown_seconds
            ):
                current_rank = (-1, -1)
            if rank <= current_rank:
                continue
            findings.append(
                Finding(
                    rule_id=rule.id,
                    rule_version=rule.version,
                    group_key=group_key,
                    tier_index=item.tier_index,
                    tier_label=item.tier.label,
                    severity=item.tier.severity,
                    points=item.tier.points,
                    window_start=item.window_start.isoformat(),
                    window_end=item.window_end.isoformat(),
                    observed=item.observed,
                    threshold=item.tier.count,
                    window_seconds=item.tier.window_seconds,
                    evidence_event_ids=item.evidence,
                    explanation=_explain(rule, group_key, item),
                )
            )
            current_rank = rank
            last_time = item.window_end
    findings.sort(key=lambda finding: finding.key)
    return findings
