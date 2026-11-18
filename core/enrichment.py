"""Offline, explainable enrichment. No DNS, GeoIP, clock or network access."""

# ruff: noqa: S104, S108 - literal classification markers, never opened or bound.
from __future__ import annotations

import ipaddress
import re
from datetime import UTC, datetime
from typing import Any

__all__ = ["enrich_event"]

_SERVICE_ACCOUNT = re.compile(r"^(daemon|www-data|nobody|systemd-.*|_.*)$")
_SUSPICIOUS_PREFIXES = ("/tmp/", "/var/tmp/", "/dev/shm/")
_ALL_INTERFACES = {"0.0.0.0", "::"}


def _scope(address: Any) -> str:
    if not address:
        return "invalid"
    try:
        parsed = ipaddress.ip_address(str(address))
    except ValueError:
        return "invalid"
    if parsed.is_loopback:
        return "loopback"
    if parsed.is_link_local:
        return "link_local"
    if parsed.is_private:
        return "private"
    return "public"


def _bind_scope(event: dict[str, Any]) -> str:
    details = event.get("details") or {}
    if isinstance(details, dict) and details.get("bind_scope"):
        return str(details["bind_scope"])
    local_ip = event.get("local_ip")
    if local_ip in _ALL_INTERFACES:
        return "all_interfaces"
    return _scope(local_ip)


def enrich_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with an ``enrichment`` dict; never mutate the input."""
    enriched = dict(event)
    values: dict[str, Any] = dict(event.get("enrichment") or {})
    values["ip_scope"] = _scope(event.get("source_ip"))
    values["destination_ip_scope"] = _scope(event.get("destination_ip"))
    username = event.get("username")
    values["is_root_user"] = username == "root"
    values["is_service_account"] = bool(username and _SERVICE_ACCOUNT.match(str(username)))
    file_path = str(event.get("file_path") or "")
    values["suspicious_path"] = file_path.startswith(_SUSPICIOUS_PREFIXES)
    values["bind_scope"] = _bind_scope(event)
    try:
        stamp = datetime.fromisoformat(str(event["timestamp"])).astimezone(UTC)
        weekdays = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        values["weekday_hour_utc"] = f"{weekdays[stamp.weekday()]}-{stamp.hour:02d}"
    except (ValueError, KeyError):
        values["weekday_hour_utc"] = "unknown"
    enriched["enrichment"] = values
    return enriched
