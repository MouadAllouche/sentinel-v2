"""Pure incident planning, titles, summaries and workflow transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from core.correlation import Component, is_anchor
from core.mitre import mitre_for_rules

__all__ = [
    "IncidentChange",
    "apply_status_transition",
    "plan_incidents",
    "summarize_incident",
    "title_for",
]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"investigating"},
    "investigating": {"resolved", "false_positive", "closed"},
    "resolved": {"investigating"},
    "false_positive": {"investigating"},
    "closed": {"investigating"},
    "merged": set(),
}
REASON_REQUIRED = {"resolved", "false_positive"}


@dataclass
class IncidentChange:
    action: str  # create | extend | merge | nochange
    incident: dict[str, Any] = field(default_factory=dict)
    absorbed: list[int] = field(default_factory=list)
    into: int | None = None


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _primary_ip(component: Component) -> str | None:
    for event in sorted(component.events, key=lambda item: str(item["timestamp"])):
        if event.get("source_ip"):
            return str(event["source_ip"])
    return None


def _primary_user(component: Component) -> str | None:
    for event in sorted(component.events, key=lambda item: str(item["timestamp"])):
        if event.get("username") and event.get("username") != "root":
            return str(event["username"])
    return None


def title_for(component: Component, findings: list[dict[str, Any]]) -> str:
    ip = _primary_ip(component) or "unknown host"
    user = _primary_user(component)
    followed = any(event.get("event_type") == "successful_login" for event in component.events)
    suffix = f" targeting {user}" if user else ""
    if followed:
        suffix += " (followed by successful login)"
    return f"Possible brute force from {ip}{suffix}"


def summarize_incident(component: Component, findings: list[dict[str, Any]]) -> str:
    events = sorted(component.events, key=lambda item: str(item["timestamp"]))
    kinds = {str(event.get("event_type")) for event in events}
    parts = [
        f"{len(events)} related events from {events[0]['timestamp']} to {events[-1]['timestamp']}.",
        f"Observed event types: {', '.join(sorted(kinds))}.",
    ]
    if findings:
        names = sorted({str(finding.get("rule_id", "rule")) for finding in findings})
        parts.append(f"Possible rule matches: {', '.join(names)}.")
    else:
        parts.append("No rule findings were attached to this grouping.")
    parts.append("Grouping is inferred from shared attributes and time proximity, not proof.")
    return " ".join(parts)


def _incident_for(component: Component, findings: list[dict[str, Any]]) -> dict[str, Any]:
    ip = _primary_ip(component)
    severities = [str(event.get("severity", "low")) for event in component.events]
    severity = max(
        severities,
        key=lambda value: {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(value, 0),
    )
    rule_ids = sorted({str(finding.get("rule_id")) for finding in findings})
    return {
        "correlation_key": component.correlation_key,
        "title": title_for(component, findings),
        "summary": summarize_incident(component, findings),
        "status": "open",
        "first_seen": min(str(event["timestamp"]) for event in component.events),
        "last_seen": max(str(event["timestamp"]) for event in component.events),
        "primary_ip": ip,
        "primary_username": _primary_user(component),
        "severity": severity,
        "mitre": mitre_for_rules(rule_ids),
        "event_ids": component.event_ids,
    }


def _creates_incident(component: Component) -> bool:
    has_strong_anchor = any(
        is_anchor(event) and str(event.get("severity", "low")) in {"medium", "high", "critical"}
        for event in component.events
    )
    has_rule = any(
        event.get("event_type") == "rule_triggered"
        and (event.get("details") or {}).get("create_incident", True) is not False
        for event in component.events
    )
    return has_strong_anchor or has_rule


def plan_incidents(
    components: list[Component],
    existing: list[dict[str, Any]],
    now: datetime,
    *,
    findings: list[dict[str, Any]] | None = None,
    reopen_after_hours: int = 6,
) -> list[IncidentChange]:
    """Plan Create/Extend/Merge/NoChange actions deterministically."""
    changes: list[IncidentChange] = []
    for component in components:
        if not _creates_incident(component):
            continue
        ids = set(component.event_ids)
        matches = [item for item in existing if ids & set(item.get("event_ids", []))]
        incident = _incident_for(component, findings or [])
        if len(matches) >= 2:
            oldest = min(matches, key=lambda item: int(item.get("id", 0)))
            changes.append(
                IncidentChange(
                    action="merge",
                    incident={**incident, "id": oldest["id"]},
                    absorbed=[int(item["id"]) for item in matches if item is not oldest],
                    into=int(oldest["id"]),
                )
            )
        elif len(matches) == 1:
            match = matches[0]
            is_closed = str(match.get("status")) in {"resolved", "false_positive", "closed"}
            stale = is_closed and (
                now - _parse(str(match["last_seen"])) > timedelta(hours=reopen_after_hours)
            )
            if stale:
                changes.append(IncidentChange(action="create", incident=incident))
            elif ids <= set(match.get("event_ids", [])):
                changes.append(
                    IncidentChange(action="nochange", incident={**incident, "id": match["id"]})
                )
            else:
                changes.append(
                    IncidentChange(action="extend", incident={**incident, "id": match["id"]})
                )
        else:
            changes.append(IncidentChange(action="create", incident=incident))
    return changes


def apply_status_transition(current: str, target: str, reason: str | None) -> str:
    """Enforce the analyst status matrix; returns the new status."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid status transition: {current} -> {target}")
    if target in REASON_REQUIRED and not (reason and reason.strip()):
        raise ValueError(f"a reason is required for status {target}")
    return target
