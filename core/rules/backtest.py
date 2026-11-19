"""Pure backtesting over historical events. No database, clock or writes."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from core.rules.models import Rule, validate_rule
from core.rules.threshold import Finding, evaluate_threshold

__all__ = ["BacktestResult", "backtest_rule"]

MAX_BACKTEST_DAYS = 30


@dataclass
class BacktestResult:
    findings: list[Finding] = field(default_factory=list)
    total_findings: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_tier: dict[int, int] = field(default_factory=dict)
    distinct_groups: int = 0
    top_groups: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, str]] = field(default_factory=list)
    samples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    noise_per_day: float = 0.0


def _in_range(event: dict[str, Any], start: datetime, end: datetime) -> bool:
    try:
        stamp = datetime.fromisoformat(str(event["timestamp"]))
    except ValueError:
        return False
    return start <= stamp <= end


def backtest_rule(
    rule_definition: dict[str, Any] | Rule,
    events: list[dict[str, Any]],
    start: str,
    end: str,
    should_stop: Callable[[], bool] | None = None,
) -> BacktestResult:
    """Evaluate an unsaved or saved rule on history without persisting anything."""
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    if end_dt < start_dt:
        raise ValueError("backtest end must not precede start")
    if end_dt - start_dt > timedelta(days=MAX_BACKTEST_DAYS):
        raise ValueError(f"backtest range must be at most {MAX_BACKTEST_DAYS} days")
    rule = (
        rule_definition if isinstance(rule_definition, Rule) else validate_rule(rule_definition)[0]
    )
    if should_stop is not None and should_stop():
        return BacktestResult()
    selected = [event for event in events if _in_range(event, start_dt, end_dt)]
    if rule.kind != "threshold":
        return BacktestResult()
    findings = evaluate_threshold(rule, selected, now=end_dt, should_stop=should_stop)
    result = BacktestResult(findings=findings, total_findings=len(findings))
    result.by_severity = dict(Counter(item.severity for item in findings))
    result.by_tier = dict(Counter(item.tier_index for item in findings))
    groups = Counter(item.group_key for item in findings)
    result.distinct_groups = len(groups)
    result.top_groups = [
        {"group_key": key, "findings": count} for key, count in groups.most_common(10)
    ]
    histogram: dict[str, int] = defaultdict(int)
    samples: dict[str, list[dict[str, Any]]] = {}
    event_by_id = {event.get("id"): event for event in selected}
    for finding in findings:
        bucket = finding.window_end[:13] + ":00:00+00:00"
        histogram[bucket] += 1
        key = str(finding.key)
        samples.setdefault(key, [])
        for identifier in finding.evidence_event_ids[:20]:
            candidate = event_by_id.get(identifier)
            if candidate is not None:
                samples[key].append(candidate)
    result.timeline = [
        {"bucket": key, "count": str(value)} for key, value in sorted(histogram.items())
    ]
    result.samples = samples
    days = max(1, (end_dt - start_dt).days)
    result.noise_per_day = len(findings) / days
    return result
