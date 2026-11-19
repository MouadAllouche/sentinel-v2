"""Pure notification rendering. Never include secrets, contents or arguments."""

from __future__ import annotations

from typing import Any

from core.notifications.models import Notification

__all__ = ["render_message"]

CAVEAT = "Automated correlation; verify before acting"


def render_message(notification: Notification) -> dict[str, Any]:
    subject = f"[{notification.severity}] {notification.title}"
    lines = [
        f"Incident: {notification.title}",
        f"Severity: {notification.severity}",
        f"Risk score: {notification.score}",
    ]
    for reason in notification.reasons[:3]:
        lines.append(f"- {reason}")
    if notification.first_seen:
        lines.append(f"First seen: {notification.first_seen}")
    if notification.last_seen:
        lines.append(f"Last seen: {notification.last_seen}")
    if notification.target:
        lines.append(f"Dashboard: {notification.target}")
    lines.append(CAVEAT)
    return {"subject": subject, "body": "\n".join(lines)}
