"""Tests for normalization and event hashing (Phase 1)."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, timedelta, timezone
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core import timeutil
from core.events import EVENT_TYPES, SOURCES, VALID_SEVERITIES, validate_event
from core.normalizer import canonicalize, compute_event_hash, normalize_event


@pytest.fixture(autouse=True)
def deterministic_local_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    """Naive timestamps are interpreted as UTC unless a test overrides this."""
    monkeypatch.setattr(timeutil, "_local_tzinfo", lambda: UTC)


def test_worked_example() -> None:
    raw = {
        "time": "2026-11-15 10:00:00",
        "action": "login_failure",
        "level": "medium",
        "message": "Failed SSH login attempt for admin",
        "user": "admin",
        "ip": "203.0.113.45",
        "source_system": "auth_log",
        "junk": 1,
    }
    assert normalize_event(raw) == {
        "timestamp": "2026-11-15T10:00:00+00:00",
        "source": "auth_log",
        "event_type": "failed_login",
        "severity": "medium",
        "description": "Failed SSH login attempt for admin",
        "username": "admin",
        "source_ip": "203.0.113.45",
    }


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("time", "timestamp"),
        ("date", "timestamp"),
        ("source_system", "source"),
        ("action", "event_type"),
        ("event", "event_type"),
        ("level", "severity"),
        ("message", "description"),
        ("user", "username"),
        ("account", "username"),
        ("ip", "source_ip"),
        ("ip_address", "source_ip"),
        ("process", "process_name"),
        ("permissions", "user_permissions"),
    ],
)
def test_every_field_alias(
    make_event: Callable[..., dict[str, Any]], alias: str, canonical: str
) -> None:
    raw = make_event(
        process_name="sshd",
        user_permissions={"before": ["user"], "after": ["root", "user"]},
    )
    value = raw.pop(canonical)
    raw[alias] = value
    assert normalize_event(raw)[canonical] == value


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("login_failure", "failed_login"),
        ("failed_password", "failed_login"),
        ("login_success", "successful_login"),
        ("permission_modified", "permission_change"),
        ("privilege_escalation", "permission_change"),
    ],
)
def test_event_type_aliases(
    make_event: Callable[..., dict[str, Any]], alias: str, expected: str
) -> None:
    assert normalize_event(make_event(event_type=alias))["event_type"] == expected


def test_canonical_field_wins_over_alias(make_event: Callable[..., dict[str, Any]]) -> None:
    assert normalize_event(make_event(username="real", user="alias"))["username"] == "real"


def test_empty_canonical_falls_back_to_alias(make_event: Callable[..., dict[str, Any]]) -> None:
    assert normalize_event(make_event(username="   ", user="alias"))["username"] == "alias"


def test_unknown_fields_dropped(make_event: Callable[..., dict[str, Any]]) -> None:
    result = normalize_event({**make_event(), "junk": 1, "cmdline": "secret"})
    assert "junk" not in result
    assert "cmdline" not in result


def test_naive_timestamp_uses_local_timezone(
    make_event: Callable[..., dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(timeutil, "_local_tzinfo", lambda: timezone(timedelta(hours=1)))
    result = normalize_event(make_event(timestamp="2026-11-15 10:00:00"))
    assert result["timestamp"] == "2026-11-15T09:00:00+00:00"


def test_aware_timestamp_normalised_to_utc(make_event: Callable[..., dict[str, Any]]) -> None:
    result = normalize_event(make_event(timestamp="2026-11-15T02:00:00+01:00"))
    assert result["timestamp"] == "2026-11-15T01:00:00+00:00"


def test_text_fields_stripped(make_event: Callable[..., dict[str, Any]]) -> None:
    result = normalize_event(
        make_event(source="  auth_log ", description="  attempt  ", username=" bob ")
    )
    assert result["source"] == "auth_log"
    assert result["description"] == "attempt"
    assert result["username"] == "bob"


def test_empty_optionals_dropped(make_event: Callable[..., dict[str, Any]]) -> None:
    result = normalize_event(make_event(username="   ", source_ip="", details={}))
    assert "username" not in result
    assert "source_ip" not in result
    assert result["details"] == {}


@pytest.mark.parametrize("bad", [None, [], "x", 42])
def test_non_dict_input_rejected(bad: object) -> None:
    with pytest.raises(ValueError):
        normalize_event(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"severity": "bogus"},
        {"description": ""},
        {"details": []},
        {"timestamp": "garbage"},
        {"source": 42},
        {"destination_port": "22"},
    ],
)
def test_invalid_result_rejected(
    make_event: Callable[..., dict[str, Any]], overrides: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        normalize_event(make_event(**overrides))


def test_details_left_untouched(make_event: Callable[..., dict[str, Any]]) -> None:
    details: dict[str, Any] = {
        "target_user": " root ",
        "flags": [" world_writable "],
        "nested": {"a": " b "},
    }
    result = normalize_event(make_event(details=details))
    assert result["details"] == details
    assert details["target_user"] == " root "


def test_network_and_permission_fields_preserved(make_event: Callable[..., dict[str, Any]]) -> None:
    raw = make_event(
        local_ip="10.0.0.5",
        destination_ip="198.51.100.9",
        destination_port=443,
        connection_status="ESTABLISHED",
        process_id=812,
        process_name="sshd",
        user_permissions={"before": ["user"], "after": ["root", "user"]},
        severity_source="override:failed_login-root",
    )
    result = normalize_event(raw)
    for field in (
        "local_ip",
        "destination_ip",
        "destination_port",
        "connection_status",
        "process_id",
        "process_name",
        "user_permissions",
        "severity_source",
    ):
        assert result[field] == raw[field]


def test_canonicalize_stable_under_key_order(make_event: Callable[..., dict[str, Any]]) -> None:
    event = make_event()
    reordered = dict(reversed(list(event.items())))
    assert canonicalize(event) == canonicalize(reordered)


def test_hash_exclusions_and_stability(make_event: Callable[..., dict[str, Any]]) -> None:
    event = make_event()
    digest = compute_event_hash(event)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    for excluded in (
        {"severity": "high"},
        {"severity_source": "rule:ssh-bruteforce-by-ip"},
        {"enrichment": {"ip_scope": "public"}},
    ):
        assert canonicalize(event) == canonicalize({**event, **excluded})
        assert compute_event_hash(event) == compute_event_hash({**event, **excluded})
    assert compute_event_hash(event) != compute_event_hash({**event, "username": "root"})
    assert compute_event_hash(event) == compute_event_hash(dict(reversed(list(event.items()))))


@settings(max_examples=100, deadline=None)
@given(
    timestamp=st.sampled_from(
        [
            "2026-11-15T10:00:00+00:00",
            "2026-11-15T10:00:00.424500+00:00",
            "2026-11-16T01:02:03+00:00",
        ]
    ),
    source=st.sampled_from(SOURCES),
    event_type=st.sampled_from(EVENT_TYPES),
    severity=st.sampled_from(VALID_SEVERITIES),
    description=st.text(min_size=1, max_size=40).filter(lambda value: bool(value.strip())),
    username=st.one_of(st.none(), st.text(max_size=10)),
)
def test_normalize_event_is_idempotent(
    timestamp: str,
    source: str,
    event_type: str,
    severity: str,
    description: str,
    username: str | None,
) -> None:
    raw: dict[str, Any] = {
        "timestamp": timestamp,
        "source": source,
        "event_type": event_type,
        "severity": severity,
        "description": description,
    }
    if username is not None:
        raw["username"] = username
    once = normalize_event(raw)
    assert validate_event(once) is True
    assert normalize_event(once) == once
