"""Pure, explained anomaly detection from simple baseline statistics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from core.baseline import Baseline
from core.rules.models import Rule
from core.rules.threshold import Finding

__all__ = ["AnomalyResult", "detect_anomaly"]


@dataclass
class AnomalyResult:
    status: str  # anomaly | normal | insufficient_baseline
    reason: str = ""
    event: dict[str, Any] | None = None
    finding: Finding | None = None


def _parse(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def detect_anomaly(
    rule: Rule,
    baseline: Baseline,
    observed: int,
    hour_start: datetime,
    now: datetime,
) -> AnomalyResult:
    """Return an anomaly event and finding for one (rule, subject, hour)."""
    del now
    if baseline.maturity != "mature":
        return AnomalyResult(status="insufficient_baseline", reason=baseline.reason)

    floor = max(baseline.stddev, rule.min_std)
    selected_index: int | None = None
    selected_tier: Any = None
    selected_threshold = 0.0
    ordered = sorted(rule.z_tiers, key=lambda item: item.z)
    for index, tier in enumerate(ordered):
        threshold = baseline.mean + tier.z * floor
        if observed >= tier.min_absolute and observed > threshold:
            # Keep scanning so the highest satisfied tier (and its canonical index) wins.
            selected_index, selected_tier, selected_threshold = index, tier, threshold
    if selected_tier is None:
        return AnomalyResult(status="normal", reason="within the expected range")

    z_observed = (observed - baseline.mean) / floor if floor else 0.0
    end = hour_start + timedelta(hours=1)
    description = (
        f"{baseline.metric}: observed {observed} in the last completed hour "
        f"({hour_start.isoformat()}..{end.isoformat()}), against a baseline mean of "
        f"{baseline.mean:.1f} (std {baseline.stddev:.1f}, {baseline.sample_count} hourly "
        f"samples over {rule.window_days} days, window {baseline.window_start} to "
        f"{baseline.window_end}); {z_observed:.1f} standard deviations above normal. "
        "This is unusual, not necessarily malicious."
    )
    details = {
        "metric": baseline.metric,
        "subject": baseline.subject,
        "observed": observed,
        "mean": baseline.mean,
        "stddev": baseline.stddev,
        "threshold": selected_threshold,
        "z_observed": z_observed,
        "tier_label": selected_tier.label,
        "window_start": baseline.window_start,
        "window_end": baseline.window_end,
        "sample_count": baseline.sample_count,
        "baseline_window_days": rule.window_days,
        "hour_start": hour_start.isoformat(),
    }
    event = {
        "timestamp": hour_start.isoformat(),
        "source": "baseline",
        "event_type": "anomaly",
        "severity": selected_tier.severity,
        "severity_source": f"rule:{rule.id}",
        "description": description,
        "details": details,
    }
    finding = Finding(
        rule_id=rule.id,
        rule_version=rule.version,
        group_key=baseline.subject,
        tier_index=selected_index if selected_index is not None else 0,
        tier_label=selected_tier.label,
        severity=selected_tier.severity,
        points=selected_tier.points,
        window_start=hour_start.isoformat(),
        window_end=end.isoformat(),
        observed=observed,
        threshold=int(selected_threshold),
        window_seconds=3600,
        evidence_event_ids=[],
        explanation=description,
    )
    return AnomalyResult(status="anomaly", event=event, finding=finding)
