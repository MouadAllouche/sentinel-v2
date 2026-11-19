"""Explainable incident timelines and groupings (observed vs inferred)."""

from __future__ import annotations

from typing import Any

from core.correlation import Component
from core.mitre import mitre_for_rules

__all__ = ["build_timeline", "explain_incident"]

ANCHOR_TYPES = frozenset(
    {
        "failed_login",
        "invalid_user",
        "rule_triggered",
        "config_drift",
        "anomaly",
        "suspicious_process",
        "user_created",
        "group_member_added",
    }
)

CAVEAT = (
    "Grouping is based on shared attributes and time proximity and is not proof of a single actor."
)


def _links_between(links: list[Any], first: int, second: int) -> list[Any]:
    return [link for link in links if {link.a, link.b} == {first, second}]


def build_timeline(
    component: Component,
    events: list[dict[str, Any]],
    links: list[Any],
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return observed events plus inferred rule statements, ordered in time."""
    ordered = sorted(
        component.events, key=lambda item: (str(item["timestamp"]), int(item.get("id", 0)))
    )
    entries: list[dict[str, Any]] = []
    previous_id: int | None = None
    for event in ordered:
        identifier = int(event.get("id", 0))
        relation = None
        if previous_id is not None:
            candidates = _links_between(links, previous_id, identifier)
            if candidates:
                link = candidates[0]
                relation = {
                    "reason": link.reason,
                    "strength": link.strength,
                    "link_kind": link.kind,
                }
        entries.append(
            {
                "timestamp": str(event["timestamp"]),
                "event_id": identifier,
                "event_type": str(event.get("event_type")),
                "severity": str(event.get("severity", "low")),
                "summary": str(event.get("description", "")),
                "kind": "observed",
                "relation_to_previous": relation,
                "rule_findings": [],
                "mitre": [],
                "_order": 0,
            }
        )
        previous_id = identifier
    for finding in findings:
        evidence = [int(value) for value in finding.get("evidence_event_ids", [])]
        timestamp = str(finding.get("window_end") or finding.get("timestamp") or "")
        entries.append(
            {
                "timestamp": timestamp,
                "event_id": None,
                "event_type": "inferred",
                "severity": str(finding.get("severity", "low")),
                "summary": f"Possible rule match: {finding.get('explanation', '')}".strip(),
                "kind": "inferred",
                "relation_to_previous": None,
                "rule_findings": [
                    {"rule_id": finding.get("rule_id"), "tier_label": finding.get("tier_label")}
                ],
                "mitre": mitre_for_rules([str(finding.get("rule_id", ""))]),
                "evidence_event_ids": evidence,
                "_order": 1,
            }
        )
    entries.sort(
        key=lambda entry: (entry["timestamp"], entry["_order"], entry.get("event_id") or 0)
    )
    for entry in entries:
        entry.pop("_order", None)
    return entries


def explain_incident(
    component: Component,
    events: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Group link reasons by strength and always include caveats."""
    strong = [link.reason for link in component.links if link.strength == "strong"]
    weak = [link.reason for link in component.links if link.strength == "weak"]
    caveats = [CAVEAT]
    caveats.extend(f"Weak link: {reason}" for reason in weak)
    return {
        "grouping": {"strong": strong, "weak": weak},
        "anchors": [
            {
                "event_id": int(event.get("id", 0)),
                "timestamp": str(event.get("timestamp", "")),
                "event_type": str(event.get("event_type", "")),
            }
            for event in sorted(events, key=lambda item: str(item.get("timestamp", "")))
            if str(event.get("event_type", "")) in ANCHOR_TYPES
        ],
        "rules": [
            {"rule_id": finding.get("rule_id"), "tier_label": finding.get("tier_label")}
            for finding in findings
        ],
        "caveats": caveats,
    }
