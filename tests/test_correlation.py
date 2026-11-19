"""Tests for pure correlation (Phase 7)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.correlation import CorrelationSettings, Link, correlate
from core.normalizer import compute_event_hash

BASE = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


def _event(
    make_event: Callable[..., dict[str, Any]],
    identifier: int,
    seconds: int,
    **overrides: Any,
) -> dict[str, Any]:
    event = make_event(
        id=identifier,
        timestamp=(BASE + timedelta(seconds=seconds)).isoformat(),
        event_type=overrides.pop("event_type", "failed_login"),
        severity=overrides.pop("severity", "medium"),
    )
    event.update(overrides)
    for key, value in list(event.items()):
        if value is None:
            del event[key]
    event["event_hash"] = compute_event_hash(event)
    return event


def _links(events: list[dict[str, Any]], **overrides: Any) -> tuple[list[Link], list[Any]]:
    settings_obj = CorrelationSettings(**overrides)
    components = correlate(events, settings_obj, now=BASE + timedelta(hours=1))
    return [link for component in components for link in component.links], components


def test_shared_ip_and_username_links(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [
        _event(make_event, 1, 0, source_ip="203.0.113.45", username="alice"),
        _event(make_event, 2, 60, source_ip="203.0.113.45", username="bob"),
    ]
    links, components = _links(events)
    assert len(components) == 1
    assert any(link.kind == "shared_ip" and link.strength == "strong" for link in links)
    assert any("203.0.113.45" in link.reason for link in links)


def test_root_username_alone_is_not_enough(make_event: Callable[..., dict[str, Any]]) -> None:
    events = [
        _event(make_event, 1, 0, source_ip=None, username="root", event_type="failed_login"),
        _event(make_event, 2, 60, source_ip=None, username="root", event_type="failed_login"),
    ]
    root_links, _components = _links(events)
    assert not any(link.kind == "shared_username_auth" for link in root_links)
    strong, components2 = _links(
        [
            {**events[0], "source_ip": "203.0.113.45"},
            {**events[1], "source_ip": "203.0.113.45"},
        ]
    )
    assert len(components2) == 1
    assert any(link.kind == "shared_ip" for link in strong)


def test_ignore_ips_and_window_boundary(make_event: Callable[..., dict[str, Any]]) -> None:
    ignored = [
        _event(make_event, 1, 0, source_ip="10.0.0.1"),
        _event(make_event, 2, 60, source_ip="10.0.0.1"),
    ]
    ignored_links, _ignored_components = _links(ignored, ignore_ips=frozenset({"10.0.0.1"}))
    assert not any(link.kind == "shared_ip" for link in ignored_links)
    far_apart = [
        _event(make_event, 1, 0, source_ip="10.0.0.2"),
        _event(make_event, 2, 901, source_ip="10.0.0.2"),
    ]
    links, _components = _links(far_apart, window_minutes=15)
    assert not any(link.kind == "shared_ip" for link in links)


def test_rule_evidence_and_group_key_links(make_event: Callable[..., dict[str, Any]]) -> None:
    base = _event(make_event, 1, 0, source_ip="203.0.113.45")
    triggered = _event(
        make_event,
        2,
        60,
        event_type="rule_triggered",
        severity="medium",
        source_ip="203.0.113.45",
        details={
            "rule_id": "ssh-bruteforce-by-ip",
            "group_key": "source_ip=203.0.113.45",
            "evidence_event_ids": [1],
        },
    )
    links, components = _links([base, triggered])
    assert len(components) == 1
    assert any(link.kind == "rule_evidence" and link.strength == "strong" for link in links)


def test_weak_links_extend_but_do_not_create(make_event: Callable[..., dict[str, Any]]) -> None:
    login = _event(
        make_event,
        1,
        0,
        event_type="successful_login",
        severity="low",
        source_ip=None,
        username="alice",
    )
    sudo = _event(
        make_event,
        2,
        60,
        event_type="sudo_command",
        severity="low",
        source_ip=None,
        username="alice",
    )
    _links_result, components = _links([login, sudo])
    assert components == []
    anchor = _event(
        make_event,
        3,
        30,
        event_type="failed_login",
        severity="medium",
        source_ip=None,
        username="alice",
    )
    links, components = _links([login, sudo, anchor])
    assert len(components) == 1
    assert any(link.kind == "follows_login_same_user" and link.strength == "weak" for link in links)


def test_host_proximity_and_shared_process(make_event: Callable[..., dict[str, Any]]) -> None:
    anchor = _event(
        make_event,
        1,
        0,
        event_type="failed_login",
        severity="medium",
        process_name="sshd",
        username="alice",
    )
    drift = _event(
        make_event,
        2,
        120,
        event_type="config_drift",
        severity="medium",
        file_path="/etc/sudoers",
        process_name="sshd",
        username="alice",
    )
    links, components = _links([anchor, drift])
    assert len(components) == 1
    kinds = {link.kind for link in links}
    assert "time_proximity_host" in kinds
    assert "shared_process" in kinds
    assert any(link.strength == "weak" for link in links)


def test_allowlist_suppression_and_span_split(make_event: Callable[..., dict[str, Any]]) -> None:
    suppressed = _event(
        make_event, 1, 0, source_ip="10.0.0.3", enrichment={"allowlist_suppressed": True}
    )
    clean = _event(make_event, 2, 60, source_ip="10.0.0.3")
    _result, components = _links([suppressed, clean])
    assert [event_id for component in components for event_id in component.event_ids] == [2]
    far = [
        _event(make_event, 1, 0, source_ip="10.0.0.4"),
        _event(make_event, 2, 90000, source_ip="10.0.0.4"),
    ]
    _links_result, components = _links(far, max_incident_span_hours=24)
    assert len(components) == 2


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(offsets=st.lists(st.integers(min_value=0, max_value=600), min_size=2, max_size=6))
def test_determinism_under_shuffle(
    offsets: list[int], make_event: Callable[..., dict[str, Any]]
) -> None:
    events = [
        _event(make_event, index, offset, source_ip="203.0.113.45")
        for index, offset in enumerate(offsets)
    ]
    first = correlate(events, CorrelationSettings(), now=BASE + timedelta(hours=1))
    shuffled = correlate(
        list(reversed(events)), CorrelationSettings(), now=BASE + timedelta(hours=1)
    )
    assert [component.correlation_key for component in first] == [
        component.correlation_key for component in shuffled
    ]
