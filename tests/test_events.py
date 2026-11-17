"""Tests for the canonical event definition (Phase 1)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from core.events import (
    EVENT_TYPES,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    SEVERITY_ORDER,
    SOURCES,
    VALID_SEVERITIES,
    max_severity,
    severity_at_least,
    validate_event,
)


def test_taxonomy_constants() -> None:
    assert set(REQUIRED_FIELDS) == {
        "timestamp",
        "source",
        "event_type",
        "severity",
        "description",
    }
    assert set(VALID_SEVERITIES) == {"low", "medium", "high", "critical"}
    assert "failed_login" in EVENT_TYPES
    assert "rule_triggered" in EVENT_TYPES
    assert len(EVENT_TYPES) == len(set(EVENT_TYPES))
    assert "auth_log" in SOURCES
    assert "baseline" in SOURCES
    assert len(SOURCES) == len(set(SOURCES))
    for field in (
        "username",
        "source_ip",
        "local_ip",
        "destination_ip",
        "destination_port",
        "connection_status",
        "process_id",
        "process_name",
        "user_permissions",
        "file_path",
        "details",
        "enrichment",
        "severity_source",
    ):
        assert field in OPTIONAL_FIELDS


def test_valid_event(make_event: Callable[..., dict[str, Any]]) -> None:
    assert validate_event(make_event()) is True


@pytest.mark.parametrize(
    "missing", ["timestamp", "source", "event_type", "severity", "description"]
)
def test_missing_required_field(make_event: Callable[..., dict[str, Any]], missing: str) -> None:
    event = make_event()
    del event[missing]
    assert validate_event(event) is False


def test_non_dict_rejected() -> None:
    assert validate_event("not a dict") is False  # type: ignore[arg-type]
    assert validate_event(None) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "   ", None, 3, "LOW"])
def test_invalid_severity(make_event: Callable[..., dict[str, Any]], bad: object) -> None:
    assert validate_event(make_event(severity=bad)) is False


@pytest.mark.parametrize("bad", ["garbage", "", None, 123])
def test_invalid_timestamp(make_event: Callable[..., dict[str, Any]], bad: object) -> None:
    assert validate_event(make_event(timestamp=bad)) is False


def test_naive_timestamp_tolerated(make_event: Callable[..., dict[str, Any]]) -> None:
    assert validate_event(make_event(timestamp="2026-11-15 10:00:00")) is True


@pytest.mark.parametrize("field", ["source", "event_type", "description"])
@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_required_text_rejected(
    make_event: Callable[..., dict[str, Any]], field: str, bad: str
) -> None:
    assert validate_event(make_event(**{field: bad})) is False


@pytest.mark.parametrize(
    "field",
    [
        "username",
        "source_ip",
        "local_ip",
        "destination_ip",
        "connection_status",
        "process_name",
        "file_path",
        "severity_source",
    ],
)
def test_optional_text_fields_must_be_strings(
    make_event: Callable[..., dict[str, Any]], field: str
) -> None:
    assert validate_event(make_event(**{field: 42})) is False
    assert validate_event(make_event(**{field: "value"})) is True


@pytest.mark.parametrize("field", ["destination_port", "process_id"])
def test_integer_fields(make_event: Callable[..., dict[str, Any]], field: str) -> None:
    assert validate_event(make_event(**{field: 22})) is True
    assert validate_event(make_event(**{field: "22"})) is False
    assert validate_event(make_event(**{field: True})) is False


@pytest.mark.parametrize("field", ["details", "enrichment"])
def test_dict_fields(make_event: Callable[..., dict[str, Any]], field: str) -> None:
    assert validate_event(make_event(**{field: {"a": 1}})) is True
    assert validate_event(make_event(**{field: ["a"]})) is False
    assert validate_event(make_event(**{field: None})) is False


def test_user_permissions_shape(make_event: Callable[..., dict[str, Any]]) -> None:
    valid = {"before": ["user"], "after": ["root", "user"]}
    assert validate_event(make_event(user_permissions=valid)) is True
    invalid: list[object] = [
        {"before": ["user"]},
        {"after": ["user"]},
        {"before": "user", "after": ["root"]},
        {"before": [1], "after": []},
        [],
        None,
    ]
    for value in invalid:
        assert validate_event(make_event(user_permissions=value)) is False


def test_unknown_keys_are_ignored(make_event: Callable[..., dict[str, Any]]) -> None:
    assert validate_event({**make_event(), "id": 1, "ingested_at": "now"}) is True


def test_severity_order_and_helpers() -> None:
    assert SEVERITY_ORDER == {"low": 0, "medium": 1, "high": 2, "critical": 3}
    for severity in VALID_SEVERITIES:
        assert max_severity(severity, severity) == severity
        assert severity_at_least(severity, severity) is True
    assert max_severity("low", "critical") == "critical"
    assert max_severity("high", "medium") == "high"
    assert severity_at_least("critical", "high") is True
    assert severity_at_least("medium", "high") is False
    with pytest.raises(ValueError):
        max_severity("bogus", "low")
    with pytest.raises(ValueError):
        severity_at_least("low", "bogus")
