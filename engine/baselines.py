"""Baseline cycle: compute summaries, detect explained anomalies, persist idempotently."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.anomaly_detection import detect_anomaly
from core.baseline import METRICS, BaselineSettings, compute_baseline, hourly_buckets
from core.timeutil import utc_now
from storage.baseline_repository import save_baseline
from storage.repositories import save_event
from storage.rules_repository import (
    get_events_for_rules,
    list_rules,
    save_findings,
)

MAX_SUBJECTS = 50


@dataclass
class BaselineReport:
    baselines_stored: int = 0
    anomalies_new: int = 0
    insufficient_baseline: int = 0


def subjects_for_metric(metric: str, events: list[dict[str, Any]]) -> list[str]:
    """Return the top-50 subjects by matching-event volume for a metric."""
    spec = METRICS[metric]
    if spec.subject_field is None:
        return ["global"]
    counts: dict[str, int] = {}
    for event in events:
        if event.get("event_type") not in spec.event_types:
            continue
        value = event.get(spec.subject_field)
        if value in (None, ""):
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [key for key, _count in ranked[:MAX_SUBJECTS]]


def _current_value(metric: str, subject: str, events: list[dict[str, Any]], now: datetime) -> int:
    buckets = hourly_buckets(events, metric, subject, window_days=1, now=now)
    return int(buckets[-1]["value"]) if buckets else 0


def run_baselines(db_path: str | Path | None = None, now: datetime | None = None) -> BaselineReport:
    reference = now or utc_now()
    report = BaselineReport()
    rules = [
        rule
        for rule in list_rules(db_path=db_path)
        if rule.kind == "baseline_metric" and rule.enabled
    ]
    if not rules:
        return report
    hour_start = reference.astimezone(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(
        hours=1
    )

    for rule in rules:
        metric = rule.metric or ""
        config = BaselineSettings(
            window_days=rule.window_days,
            min_samples=rule.min_samples,
            min_history_hours=rule.min_history_hours,
        )
        since = (reference - timedelta(days=rule.window_days)).isoformat()
        events = get_events_for_rules(since, db_path)
        subjects = (
            [rule.subject or "global"]
            if rule.subject != "*"
            else subjects_for_metric(metric, events)
        )
        for subject in subjects[:MAX_SUBJECTS]:
            baseline = compute_baseline(events, metric, subject, now=reference, settings=config)
            if save_baseline(baseline, db_path):
                report.baselines_stored += 1
            observed = _current_value(metric, subject, events, reference)
            result = detect_anomaly(rule, baseline, observed, hour_start, reference)
            if result.status == "insufficient_baseline":
                report.insufficient_baseline += 1
                continue
            if result.status != "anomaly" or result.event is None or result.finding is None:
                continue
            identifier = save_event(result.event, db_path, severity_source=f"rule:{rule.id}")
            saved = save_findings([result.finding], db_path)
            if identifier is not None and saved and saved[0][1]:
                report.anomalies_new += 1
    return report
