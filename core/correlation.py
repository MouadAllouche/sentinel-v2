"""Pure correlation: turn events into explained, ordered components.

Correlation is inference, never proof. Every link carries plain-language text and
a strength; weak links can extend a component but never create one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

__all__ = ["Component", "CorrelationSettings", "Link", "correlate", "is_anchor"]

AUTH_EVENTS = frozenset(
    {"failed_login", "successful_login", "invalid_user", "sudo_command", "su_command"}
)
HOST_EVENTS = frozenset(
    {
        "config_drift",
        "user_created",
        "group_member_added",
        "new_listening_port",
        "package_installed",
    }
)
FOLLOW_EVENTS = frozenset({"sudo_command", "su_command", "process_started", "network_connection"})
ANCHOR_EVENTS = frozenset(
    {
        "failed_login",
        "invalid_user",
        "rule_triggered",
        "anomaly",
        "suspicious_process",
        "user_created",
        "group_member_added",
    }
)


@dataclass(frozen=True)
class CorrelationSettings:
    window_minutes: int = 15
    max_incident_span_hours: int = 24
    ignore_ips: frozenset[str] = frozenset()
    ignore_usernames_for_linking: tuple[str, ...] = ("root",)
    reopen_after_hours: int = 6


@dataclass(frozen=True)
class Link:
    a: int
    b: int
    kind: str
    strength: str
    reason: str


@dataclass
class Component:
    events: list[dict[str, Any]] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)

    @property
    def event_ids(self) -> list[int]:
        return sorted(int(event.get("id", 0)) for event in self.events)

    @property
    def correlation_key(self) -> str:
        anchors = [event for event in self.events if is_anchor(event)]
        chosen = anchors or self.events
        earliest = min(chosen, key=lambda event: (str(event["timestamp"]), int(event.get("id", 0))))
        return str(earliest.get("event_hash") or f"event-{earliest.get('id', 0)}")

    @property
    def span_seconds(self) -> float:
        times = sorted(str(event["timestamp"]) for event in self.events)
        if not times:
            return 0.0
        return (_parse(times[-1]) - _parse(times[0])).total_seconds()


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _gap(seconds: float) -> str:
    minutes, remainder = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {remainder}s"
    return f"{remainder}s"


def is_anchor(event: dict[str, Any]) -> bool:
    kind = str(event.get("event_type"))
    if kind == "config_drift":
        return str(event.get("severity")) in {"medium", "high", "critical"}
    return kind in ANCHOR_EVENTS


def _suppressed(event: dict[str, Any]) -> bool:
    enrichment = event.get("enrichment") or {}
    return isinstance(enrichment, dict) and enrichment.get("allowlist_suppressed") is True


def _link_pair(
    first: dict[str, Any],
    second: dict[str, Any],
    delta: float,
    settings: CorrelationSettings,
    *,
    weak: bool = True,
    strong_ids: set[int] | None = None,
) -> list[Link]:
    first_id, second_id = int(first.get("id", 0)), int(second.get("id", 0))
    links: list[Link] = []
    gap = _gap(delta)
    first_ip, second_ip = first.get("source_ip"), second.get("source_ip")
    if first_ip and first_ip == second_ip and str(first_ip) not in settings.ignore_ips:
        links.append(
            Link(
                first_id,
                second_id,
                "shared_ip",
                "strong",
                f"Same source IP {first_ip}; {gap} after the previous event",
            )
        )
    username = first.get("username")
    if (
        username
        and username == second.get("username")
        and str(username) not in settings.ignore_usernames_for_linking
        and first.get("event_type") in AUTH_EVENTS
        and second.get("event_type") in AUTH_EVENTS
    ):
        links.append(
            Link(
                first_id,
                second_id,
                "shared_username_auth",
                "strong",
                f"Same username {username} on authentication events; {gap} apart",
            )
        )
    for rule_event, evidence_event in ((first, second), (second, first)):
        if rule_event.get("event_type") != "rule_triggered":
            continue
        details = rule_event.get("details") or {}
        evidence_ids = details.get("evidence_event_ids") or []
        if int(evidence_event.get("id", 0)) in evidence_ids:
            links.append(
                Link(
                    first_id,
                    second_id,
                    "rule_evidence",
                    "strong",
                    f"Rule evidence: '{details.get('rule_id', 'rule')}' "
                    f"matched this {evidence_event.get('event_type')}; {gap} apart",
                )
            )
            break
    if (
        first.get("event_type") == "rule_triggered"
        and second.get("event_type") == "rule_triggered"
        and (first.get("details") or {}).get("group_key")
        == (second.get("details") or {}).get("group_key")
    ):
        links.append(
            Link(
                first_id,
                second_id,
                "same_group_key",
                "strong",
                "Two rule findings share the same group key",
            )
        )
    if not weak:
        return links
    if (
        first.get("event_type") == "successful_login"
        and second.get("event_type") in FOLLOW_EVENTS
        and first.get("username")
        and first.get("username") == second.get("username")
    ):
        links.append(
            Link(
                first_id,
                second_id,
                "follows_login_same_user",
                "weak",
                f"Weak: {second.get('event_type')} {gap} after a successful login "
                f"by {first.get('username')}; no shared IP",
            )
        )
    if second.get("event_type") in HOST_EVENTS and (strong_ids is None or first_id in strong_ids):
        links.append(
            Link(
                first_id,
                second_id,
                "time_proximity_host",
                "weak",
                f"Weak: {second.get('event_type')} occurred {gap} after "
                f"{first.get('event_type')}; time proximity only",
            )
        )
    if (
        first.get("process_name")
        and first.get("process_name") == second.get("process_name")
        and first.get("username")
        and first.get("username") == second.get("username")
    ):
        links.append(
            Link(
                first_id,
                second_id,
                "shared_process",
                "weak",
                f"Weak: shared process {first.get('process_name')} "
                f"for {first.get('username')}; {gap} apart",
            )
        )
    return links


class _UnionFind:
    def __init__(self, identifiers: list[int]) -> None:
        self.parent = {identifier: identifier for identifier in identifiers}

    def find(self, identifier: int) -> int:
        parent = self.parent[identifier]
        while parent != identifier:
            identifier = parent
            parent = self.parent[identifier]
        return identifier

    def union(self, first: int, second: int) -> None:
        self.parent[self.find(second)] = self.find(first)


def _split_component(component: Component, max_span: float) -> list[Component]:
    if component.span_seconds <= max_span or len(component.events) < 2:
        return [component]
    parts: list[Component] = []
    current: list[dict[str, Any]] = []
    for event in component.events:
        if (
            current
            and (
                _parse(str(event["timestamp"])) - _parse(str(current[0]["timestamp"]))
            ).total_seconds()
            > max_span
        ):
            parts.append(Component(events=current))
            current = []
        current.append(event)
    if current:
        parts.append(Component(events=current))
    result: list[Component] = []
    for part in parts:
        if not any(is_anchor(event) for event in part.events):
            continue
        ids = {event["id"] for event in part.events}
        result.append(
            Component(
                events=part.events,
                links=[link for link in component.links if link.a in ids and link.b in ids],
            )
        )
    return result


def correlate(
    events: list[dict[str, Any]], settings: CorrelationSettings, now: datetime
) -> list[Component]:
    """Return deterministic components; ``now`` is accepted for API symmetry."""
    del now
    usable = sorted(
        (
            event
            for event in events
            if isinstance(event, dict)
            and "timestamp" in event
            and "event_type" in event
            and not _suppressed(event)
        ),
        key=lambda item: (str(item["timestamp"]), int(item.get("id", 0))),
    )
    identifiers = [int(event.get("id", 0)) for event in usable]
    if not identifiers:
        return []
    links: list[Link] = []
    pairs: list[tuple[dict[str, Any], dict[str, Any], float]] = []
    window = timedelta(minutes=settings.window_minutes)
    for index, first in enumerate(usable):
        for second in usable[index + 1 :]:
            delta = (
                _parse(str(second["timestamp"])) - _parse(str(first["timestamp"]))
            ).total_seconds()
            if delta > window.total_seconds():
                break
            pairs.append((first, second, delta))
    for first, second, delta in pairs:
        links.extend(_link_pair(first, second, delta, settings, weak=False))
    strong_ids = {identifier for link in links for identifier in (link.a, link.b)}
    for first, second, delta in pairs:
        links.extend(_link_pair(first, second, delta, settings, weak=True, strong_ids=strong_ids))

    union = _UnionFind(identifiers)
    for link in links:
        union.union(link.a, link.b)
    groups: dict[int, list[dict[str, Any]]] = {}
    for event in usable:
        groups.setdefault(union.find(int(event.get("id", 0))), []).append(event)

    components: list[Component] = []
    for group in groups.values():
        ids = {int(event.get("id", 0)) for event in group}
        group_links = [link for link in links if link.a in ids and link.b in ids]
        component = Component(events=group, links=group_links)
        # Weak links alone cannot create a component; an anchor is required.
        if not any(is_anchor(event) for event in group):
            continue
        components.extend(_split_component(component, settings.max_incident_span_hours * 3600))
    components.sort(key=lambda component: (component.correlation_key, component.event_ids))
    return components
