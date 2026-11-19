"""Pure hourly behavioural statistics. No machine learning, clock or I/O."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

__all__ = ["Baseline", "BaselineSettings", "METRICS", "compute_baseline", "hourly_buckets"]


@dataclass(frozen=True)
class MetricSpec:
    subject_field: str | None
    event_types: frozenset[str]
    distinct_field: str | None = None


METRICS: dict[str, MetricSpec] = {
    "failed_logins_per_hour": MetricSpec(None, frozenset({"failed_login", "invalid_user"})),
    "failed_logins_per_hour_by_ip": MetricSpec("source_ip", frozenset({"failed_login"})),
    "successful_logins_per_hour": MetricSpec("username", frozenset({"successful_login"})),
    "new_connections_per_hour": MetricSpec("process_name", frozenset({"network_connection"})),
    "distinct_destinations_per_hour": MetricSpec(
        "process_name", frozenset({"network_connection"}), "destination_ip"
    ),
    "sudo_commands_per_hour": MetricSpec("username", frozenset({"sudo_command"})),
    "known_login_ips": MetricSpec("username", frozenset({"successful_login"}), "source_ip"),
}


@dataclass(frozen=True)
class BaselineSettings:
    window_days: int = 7
    min_samples: int = 24
    min_history_hours: int = 24
    hour_of_week: bool = False


@dataclass(frozen=True)
class Baseline:
    metric: str
    subject: str
    window_start: str
    window_end: str
    mean: float
    stddev: float
    sample_count: int
    maximum: float
    p95: float
    maturity: str
    reason: str
    buckets: tuple[dict[str, Any], ...] = field(default=(), repr=False)


def _parse(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _usable(event: Any) -> bool:
    if not isinstance(event, dict) or "timestamp" not in event or "event_type" not in event:
        return False
    if event.get("source") in {"baseline", "rules"}:
        return False
    enrichment = event.get("enrichment") or {}
    return not (isinstance(enrichment, dict) and enrichment.get("allowlist_suppressed") is True)


def _window(now: datetime, window_days: int) -> tuple[datetime, datetime]:
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    start = end - timedelta(hours=max(1, window_days) * 24 - 1)
    return start, end


def hourly_buckets(
    events: list[dict[str, Any]],
    metric: str,
    subject: str,
    *,
    window_days: int = 7,
    now: datetime,
) -> list[dict[str, Any]]:
    """Return zero-filled hourly buckets for one metric/subject."""
    spec = METRICS[metric]
    start, end = _window(now, window_days)
    counts: dict[str, int] = {}
    distinct: dict[str, set[str]] = {}
    for event in events:
        if not _usable(event) or event.get("event_type") not in spec.event_types:
            continue
        if spec.subject_field and str(event.get(spec.subject_field)) != subject:
            continue
        try:
            stamp = _parse(event["timestamp"])
        except ValueError:
            continue
        if not start <= stamp <= end:
            continue
        key = stamp.replace(minute=0, second=0, microsecond=0).isoformat()
        if spec.distinct_field:
            value = event.get(spec.distinct_field)
            if value is None:
                continue
            distinct.setdefault(key, set()).add(str(value))
        else:
            counts[key] = counts.get(key, 0) + 1
    buckets: list[dict[str, Any]] = []
    current = start
    while current <= end:
        key = current.isoformat()
        buckets.append(
            {
                "timestamp": key,
                "value": len(distinct.get(key, set()))
                if spec.distinct_field
                else counts.get(key, 0),
            }
        )
        current += timedelta(hours=1)
    return buckets


def _oldest(events: list[dict[str, Any]], metric: str, subject: str) -> datetime | None:
    spec = METRICS[metric]
    stamps: list[datetime] = []
    for event in events:
        if not _usable(event):
            continue
        relevant = event.get("event_type") in spec.event_types and (
            not spec.subject_field or str(event.get(spec.subject_field)) == subject
        )
        if relevant:
            try:
                stamps.append(_parse(event["timestamp"]))
            except ValueError:
                continue
    if not stamps:
        for event in events:
            try:
                stamps.append(_parse(event["timestamp"]))
            except (ValueError, KeyError, TypeError):
                continue
    return min(stamps) if stamps else None


def compute_baseline(
    events: list[dict[str, Any]],
    metric: str,
    subject: str,
    *,
    now: datetime,
    settings: BaselineSettings | None = None,
) -> Baseline:
    """Compute a zero-filled hourly baseline and its maturity."""
    config = settings or BaselineSettings()
    buckets = hourly_buckets(events, metric, subject, window_days=config.window_days, now=now)
    values = [float(item["value"]) for item in buckets]
    count = len(values)
    mean = sum(values) / count if count else 0.0
    stddev = math.sqrt(sum((value - mean) ** 2 for value in values) / count) if count else 0.0
    ordered = sorted(values)
    p95 = ordered[math.ceil(0.95 * count) - 1] if count else 0.0
    start, end = _window(now, config.window_days)

    reasons: list[str] = []
    if count < config.min_samples:
        reasons.append(f"only {count} hourly samples; need {config.min_samples}")
    oldest = _oldest(events, metric, subject)
    history_hours = (now - oldest).total_seconds() / 3600 if oldest else 0.0
    if history_hours < config.min_history_hours:
        reasons.append(
            f"only {int(history_hours)} hours of history; need {config.min_history_hours}"
        )
    if config.hour_of_week and history_hours < 4 * 7 * 24:
        reasons.append("hour-of-week profile needs 4 weeks; using global hourly baseline")
    maturity = (
        "immature"
        if (count < config.min_samples or history_hours < config.min_history_hours)
        else "mature"
    )

    return Baseline(
        metric=metric,
        subject=subject,
        window_start=start.isoformat(),
        window_end=end.isoformat(),
        mean=mean,
        stddev=stddev,
        sample_count=count,
        maximum=max(values) if values else 0.0,
        p95=p95,
        maturity=maturity,
        reason="; ".join(reasons),
        buckets=tuple(buckets),
    )
