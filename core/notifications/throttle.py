"""Pure notification routing and throttling decisions."""

from __future__ import annotations

from datetime import datetime

from core.events import SEVERITY_ORDER
from core.notifications.models import Channel, Notification

__all__ = ["should_send"]


def _quiet(channel: Channel, now: datetime) -> bool:
    hours = (channel.filters or {}).get("quiet_hours") or {}
    if not hours:
        return False
    start, end = int(hours.get("start", 0)), int(hours.get("end", 0))
    if start <= end:
        return start <= now.hour < end
    return now.hour >= start or now.hour < end


def should_send(
    channel: Channel,
    notification: Notification,
    history: list[datetime],
    now: datetime,
) -> bool:
    if not channel.enabled:
        return False
    actual = int(SEVERITY_ORDER.get(notification.severity, 0))
    minimum = int(SEVERITY_ORDER.get(channel.min_severity, 0))
    if actual < minimum:
        return False
    filters = channel.filters or {}
    allowed_statuses = filters.get("statuses")
    if allowed_statuses and notification.status not in allowed_statuses:
        return False
    if _quiet(channel, now):
        return False
    throttle = channel.throttle or {}
    cooldown = int(throttle.get("cooldown_minutes", 0))
    if cooldown and any(0 <= (now - sent).total_seconds() <= cooldown * 60 for sent in history):
        return False
    maximum = int(throttle.get("max_per_hour", 0))
    if maximum and sum((now - sent).total_seconds() < 3600 for sent in history) >= maximum:
        return False
    if throttle.get("digest_minutes"):
        return True  # digest mode batches; delivery decision is deferred
    return True
