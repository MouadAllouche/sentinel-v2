"""Tests for event, state, audit and settings repositories (Phase 2)."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

from core.events import VALID_SEVERITIES
from core.normalizer import compute_event_hash
from storage.database import get_connection
from storage.repositories import (
    count_events,
    event_time_series,
    get_event,
    get_events_by_ids,
    get_setting,
    get_state,
    list_audit,
    query_events,
    save_event,
    save_events,
    set_setting,
    set_state,
    top_values,
    write_audit,
)


def _save_allowing(path: Path, event: dict[str, Any], *, allowlisted: bool = False) -> int | None:
    return save_event(event, path, allowlisted=allowlisted)


def test_save_event_id_and_round_trip(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    event = make_event()
    event_id = save_event(event, tmp_initialised_db)
    assert event_id == 1
    stored = get_event(event_id, tmp_initialised_db)
    assert stored is not None
    for key, value in event.items():
        assert stored[key] == value
    assert stored["id"] == event_id
    assert stored["allowlisted"] is False


def test_duplicate_event_is_ignored(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    assert save_event(make_event(), tmp_initialised_db) == 1
    assert save_event(make_event(), tmp_initialised_db) is None
    assert count_events({}, tmp_initialised_db) == 1


def test_batch_save_is_one_transaction(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    events = [make_event(description=f"batch-{index}") for index in range(5)]
    identifiers = save_events(events, tmp_initialised_db)
    assert all(identifier is not None for identifier in identifiers)
    assert count_events({}, tmp_initialised_db) == 5
    assert save_events([events[0]], tmp_initialised_db) == [None]


def test_invalid_and_naive_events_rejected(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    with pytest.raises(ValueError):
        save_event(make_event(severity="bogus"), tmp_initialised_db)
    with pytest.raises(ValueError):
        save_event(make_event(timestamp="2026-11-15 10:00:00"), tmp_initialised_db)
    with pytest.raises(ValueError):
        save_event("not an event", tmp_initialised_db)  # type: ignore[arg-type]


def test_promoted_columns_match_stored_json(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    event = make_event(
        process_name="sshd",
        destination_ip="198.51.100.9",
        file_path="/etc/ssh/sshd_config",
        username="admin",
    )
    event_id = save_event(event, tmp_initialised_db)
    assert event_id is not None
    connection = get_connection(tmp_initialised_db)
    row = connection.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    connection.close()
    assert row is not None
    document = json.loads(row["event_data"])
    for column in (
        "timestamp",
        "source",
        "event_type",
        "severity",
        "severity_source",
        "username",
        "source_ip",
        "process_name",
        "destination_ip",
        "file_path",
    ):
        assert row[column] == document[column]
    assert row["event_hash"] == compute_event_hash(event)
    assert row["allowlisted"] == 0


def test_unknown_keys_never_stored(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    event_id = save_event({**make_event(), "cmdline": "sshd --password=secret"}, tmp_initialised_db)
    assert event_id is not None
    stored = get_event(event_id, tmp_initialised_db)
    assert stored is not None
    assert "cmdline" not in stored
    connection = get_connection(tmp_initialised_db)
    raw = connection.execute("SELECT event_data FROM events WHERE id = ?", (event_id,)).fetchone()[
        0
    ]
    connection.close()
    assert "cmdline" not in raw
    assert "secret" not in raw


def test_severity_source_does_not_change_identity(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    event = make_event()
    first = save_event(event, tmp_initialised_db, severity_source="default")
    connection = get_connection(tmp_initialised_db)
    first_hash = connection.execute(
        "SELECT event_hash FROM events WHERE id = ?", (first,)
    ).fetchone()[0]
    connection.close()
    assert save_event(event, tmp_initialised_db, severity_source="rule:ssh-bruteforce") is None
    # A different identity row is impossible, so verify the source is set on insert.
    other = make_event(description="different identity")
    second = save_event(other, tmp_initialised_db, severity_source="rule:ssh-bruteforce")
    assert second is not None
    stored = get_event(second, tmp_initialised_db)
    assert stored is not None
    assert stored["severity_source"] == "rule:ssh-bruteforce"
    assert first_hash == compute_event_hash(event)


def test_get_events_by_ids(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    first = save_event(make_event(description="one"), tmp_initialised_db)
    second = save_event(make_event(description="two"), tmp_initialised_db)
    result = get_events_by_ids([first, second, 9999], tmp_initialised_db)  # type: ignore[list-item]
    assert set(result) == {first, second}
    assert result[first]["description"] == "one"  # type: ignore[index]


@pytest.fixture
def filtered_db(tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]) -> Path:
    _save_allowing(
        tmp_initialised_db,
        make_event(
            description="alpha failed",
            event_type="failed_login",
            severity="low",
            source="auth_log",
            username="alice",
            source_ip="203.0.113.10",
            process_name="sshd",
            timestamp="2026-11-15T10:00:00+00:00",
        ),
    )
    _save_allowing(
        tmp_initialised_db,
        make_event(
            description="beta success",
            event_type="successful_login",
            severity="medium",
            source="journald",
            username="bob",
            source_ip="203.0.113.11",
            process_name="sudo",
            timestamp="2026-11-15T11:00:00+00:00",
        ),
    )
    _save_allowing(
        tmp_initialised_db,
        make_event(
            description="gamma drift",
            event_type="config_drift",
            severity="high",
            source="filesystem",
            username="carol",
            source_ip="203.0.113.12",
            process_name="systemd",
            timestamp="2026-11-16T10:00:00+00:00",
        ),
        allowlisted=True,
    )
    return tmp_initialised_db


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"event_type": ["failed_login"]}, {"alpha failed"}),
        ({"severity": ["high", "medium"]}, {"beta success", "gamma drift"}),
        ({"source": ["journald"]}, {"beta success"}),
        ({"username": "carol"}, {"gamma drift"}),
        ({"source_ip": "203.0.113.10"}, {"alpha failed"}),
        ({"process_name": "sudo"}, {"beta success"}),
        ({"since": "2026-11-15T10:30:00+00:00"}, {"beta success", "gamma drift"}),
        ({"until": "2026-11-15T10:30:00+00:00"}, {"alpha failed"}),
        ({"search": "gamma"}, {"gamma drift"}),
        ({"allowlisted": True}, {"gamma drift"}),
        ({"allowlisted": False}, {"alpha failed", "beta success"}),
        (
            {
                "event_type": ["failed_login"],
                "source_ip": "203.0.113.10",
                "since": "2026-11-15T09:00:00+00:00",
                "until": "2026-11-15T11:00:00+00:00",
            },
            {"alpha failed"},
        ),
    ],
)
def test_query_filters(filtered_db: Path, filters: dict[str, Any], expected: set[str]) -> None:
    page = query_events(filters, db_path=filtered_db)
    assert {item["description"] for item in page["items"]} == expected
    assert count_events(filters, filtered_db) == len(expected)


def test_search_treats_wildcards_literally(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    save_events(
        [
            make_event(description="rate 100% complete"),
            make_event(description="rate 100X complete"),
            make_event(description="token a_b value"),
            make_event(description="token axb value"),
        ],
        tmp_initialised_db,
    )
    assert {
        item["description"]
        for item in query_events({"search": "100%"}, db_path=tmp_initialised_db)["items"]
    } == {"rate 100% complete"}
    assert {
        item["description"]
        for item in query_events({"search": "a_b"}, db_path=tmp_initialised_db)["items"]
    } == {"token a_b value"}


def test_event_severity_source_preserved(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    event = make_event(severity_source="override:failed_login-root")
    event_id = save_event(event, tmp_initialised_db)
    assert event_id is not None
    stored = get_event(event_id, tmp_initialised_db)
    assert stored is not None
    assert stored["severity_source"] == "override:failed_login-root"


def test_scalar_list_filter_rejected(filtered_db: Path) -> None:
    with pytest.raises(ValueError, match="sequence"):
        query_events({"event_type": "failed_login"}, db_path=filtered_db)


def test_incident_filter_uses_incident_events(filtered_db: Path) -> None:
    assert query_events({"incident_id": 1}, db_path=filtered_db)["items"] == []


def test_query_ordering_and_keyset_pagination(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    events = [make_event(description=f"page-{index}") for index in range(250)]
    save_events(events, tmp_initialised_db)
    identifiers: list[int] = []
    cursor: str | None = None
    pages = 0
    while True:
        page = query_events({}, cursor=cursor, limit=50, db_path=tmp_initialised_db)
        identifiers.extend(item["id"] for item in page["items"])
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
        assert pages < 20
    assert pages == 5
    assert len(identifiers) == 250
    assert len(set(identifiers)) == 250
    assert identifiers == list(range(250, 0, -1))


def test_query_rejects_invalid_cursor(filtered_db: Path) -> None:
    with pytest.raises(ValueError):
        query_events({}, cursor="not-a-cursor!", db_path=filtered_db)


def test_event_time_series_and_zero_fill(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    save_events(
        [
            make_event(
                description=f"hour-{index}",
                timestamp=f"2026-11-15T{10 + index // 2:02d}:00:00+00:00",
            )
            for index in range(3)
        ],
        tmp_initialised_db,
    )
    hourly = event_time_series({}, bucket="hour", db_path=tmp_initialised_db)
    assert hourly == {
        "2026-11-15T10:00:00+00:00": 2,
        "2026-11-15T11:00:00+00:00": 1,
    }
    filled = event_time_series(
        {
            "since": "2026-11-15T10:00:00+00:00",
            "until": "2026-11-15T12:00:00+00:00",
        },
        bucket="hour",
        zero_fill=True,
        db_path=tmp_initialised_db,
    )
    assert filled == {
        "2026-11-15T10:00:00+00:00": 2,
        "2026-11-15T11:00:00+00:00": 1,
        "2026-11-15T12:00:00+00:00": 0,
    }
    daily = event_time_series({}, bucket="day", db_path=tmp_initialised_db)
    assert daily == {"2026-11-15T00:00:00+00:00": 3}


def test_top_values(filtered_db: Path) -> None:
    values = top_values("event_type", db_path=filtered_db)
    # Equal counts are ordered by value ascending (total DESC, value ASC).
    assert values == [
        {"value": "config_drift", "count": 1},
        {"value": "failed_login", "count": 1},
        {"value": "successful_login", "count": 1},
    ]
    with pytest.raises(ValueError):
        top_values("description", db_path=filtered_db)


def test_state_round_trip(tmp_initialised_db: Path) -> None:
    assert get_state("missing", tmp_initialised_db) is None
    set_state("cursor", {"offset": 123}, tmp_initialised_db)
    assert get_state("cursor", tmp_initialised_db) == {"offset": 123}
    set_state("cursor", {"offset": 124}, tmp_initialised_db)
    assert get_state("cursor", tmp_initialised_db) == {"offset": 124}


def test_audit_write_and_list(tmp_initialised_db: Path) -> None:
    audit_id = write_audit(
        "alice",
        "rule.update",
        target_type="rule",
        target_id="ssh-bruteforce-by-ip",
        before={"enabled": True},
        after={"enabled": False},
        ip="127.0.0.1",
        db_path=tmp_initialised_db,
    )
    assert audit_id > 0
    items = list_audit({}, db_path=tmp_initialised_db)["items"]
    assert len(items) == 1
    assert items[0]["actor"] == "alice"
    assert items[0]["before"] == {"enabled": True}
    assert items[0]["after"] == {"enabled": False}
    assert items[0]["ip"] == "127.0.0.1"
    assert list_audit({"action_prefix": "rule."}, db_path=tmp_initialised_db)["items"] == items
    assert list_audit({"actor": "bob"}, db_path=tmp_initialised_db)["items"] == []
    with pytest.raises(ValueError, match="limit"):
        list_audit({}, limit=0, db_path=tmp_initialised_db)


def test_settings_round_trip(tmp_initialised_db: Path) -> None:
    assert get_setting("risk.thresholds", tmp_initialised_db) is None
    set_setting("risk.thresholds", {"critical": 70}, updated_by="alice", db_path=tmp_initialised_db)
    assert get_setting("risk.thresholds", tmp_initialised_db) == {"critical": 70}
    connection = get_connection(tmp_initialised_db)
    row = connection.execute(
        "SELECT updated_by FROM app_settings WHERE key = ?", ("risk.thresholds",)
    ).fetchone()
    connection.close()
    assert row[0] == "alice"


def test_concurrent_writers(
    tmp_initialised_db: Path, make_event: Callable[..., dict[str, Any]]
) -> None:
    errors: list[BaseException] = []

    def worker(prefix: str) -> None:
        try:
            save_events(
                [make_event(description=f"{prefix}-{index}") for index in range(20)],
                tmp_initialised_db,
            )
        except BaseException as exc:  # noqa: BLE001 - report the failure via the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(prefix,)) for prefix in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert count_events({}, tmp_initialised_db) == 40


@hypothesis_settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    description=st.uuids().map(str),
    severity=st.sampled_from(VALID_SEVERITIES),
    username=st.text(min_size=1, max_size=12),
)
def test_save_get_round_trip_preserves_event(
    tmp_initialised_db: Path,
    make_event: Callable[..., dict[str, Any]],
    description: str,
    severity: str,
    username: str,
) -> None:
    event = make_event(description=description, severity=severity, username=username)
    event_id = save_event(event, tmp_initialised_db)
    assert event_id is not None
    stored = get_event(event_id, tmp_initialised_db)
    assert stored is not None
    for key, value in event.items():
        assert stored[key] == value


def test_storage_sql_is_parameterised() -> None:
    storage_dir = Path(__file__).resolve().parents[1] / "storage"
    for path in storage_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert 'execute(f"' not in source
        assert "execute(f'" not in source
        assert 'executemany(f"' not in source
