"""Tests for allowlist matching and offline enrichment (Phase 4)."""

# ruff: noqa: S108 - test fixture path models a suspicious executable, never opened.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from core.allowlist import Entry, matches, reduce_severity, validate_entry
from core.enrichment import enrich_event
from core.events import validate_event


def _entry(**overrides: Any) -> Entry:
    data: dict[str, Any] = {
        "id": 1,
        "kind": "ip",
        "value": "203.0.113.45",
        "scope": "annotate",
        "reason": "trusted scanner",
        "expires_at": None,
        "enabled": True,
    }
    data.update(overrides)
    return validate_entry(data)


def test_each_kind_matches(make_event: Any) -> None:
    event = make_event(
        event_type="failed_login",
        source_ip="203.0.113.45",
        process_name="visudo",
        file_path="/etc/sudoers",
    )
    cases = [
        ("ip", "203.0.113.45", True),
        ("ip", "198.51.100.7", False),
        ("cidr", "203.0.113.0/24", True),
        ("username", "admin", True),
        ("command", "visudo", True),
        ("event_type", "failed_login", True),
        ("path", "/etc/sudoers", True),
    ]
    for kind, value, expected in cases:
        assert (
            bool(
                matches(
                    event, [_entry(kind=kind, value=value)], now=datetime(2026, 11, 15, tzinfo=UTC)
                )
            )
            is expected
        )


def test_scopes_and_validation(make_event: Any) -> None:
    for scope in ("annotate", "suppress_alerts", "lower_severity"):
        assert _entry(scope=scope).scope == scope
    with pytest.raises(ValueError, match="reason"):
        _entry(reason="abc")
    with pytest.raises(ValueError, match="kind"):
        _entry(kind="magic")
    with pytest.raises(ValueError, match="scope"):
        _entry(scope="delete")
    assert reduce_severity("critical") == "high"
    assert reduce_severity("low") == "low"


def test_expiry_and_disabled(make_event: Any) -> None:
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    future = (now + timedelta(minutes=1)).isoformat()
    past = (now - timedelta(minutes=1)).isoformat()
    assert matches(make_event(), [_entry(expires_at=future)], now) != []
    assert matches(make_event(), [_entry(expires_at=past)], now) == []
    assert matches(make_event(), [_entry(expires_at=now.isoformat())], now) == []
    assert matches(make_event(), [_entry(enabled=False)], now) == []


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("127.0.0.1", "loopback"),
        ("10.0.0.5", "private"),
        ("169.254.1.1", "link_local"),
        ("8.8.8.8", "public"),
        ("not-an-ip", "invalid"),
        ("2001:db8::1", "private"),
    ],
)
def test_enrichment_ip_scopes(make_event: Any, address: str, expected: str) -> None:
    event = make_event(source_ip=address)
    enriched = enrich_event(event)
    assert enriched["enrichment"]["ip_scope"] == expected
    assert validate_event(enriched) is True


def test_enrichment_fields_and_no_mutation(make_event: Any) -> None:
    event = make_event(
        username="root",
        process_name="visudo",
        file_path="/tmp/payload",
        destination_ip="8.8.8.8",
        details={"bind_scope": "all_interfaces"},
    )
    original_details = dict(event["details"])
    enriched = enrich_event(event)
    assert event.get("enrichment") is None
    assert event["details"] == original_details
    values = enriched["enrichment"]
    assert values["is_root_user"] is True
    assert values["suspicious_path"] is True
    assert values["bind_scope"] == "all_interfaces"
    assert values["destination_ip_scope"] == "public"
    assert values["weekday_hour_utc"] == "Sun-10"
    assert values["is_service_account"] is False
    assert enrich_event(make_event(username="www-data"))["enrichment"]["is_service_account"] is True
