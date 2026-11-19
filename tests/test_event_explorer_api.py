"""Phase 14 storage/API support for the Overview and Events explorer."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

from storage.database import get_connection
from storage.repositories import (
    event_time_series_by_severity,
    query_events,
    query_events_bulk,
    save_events,
)


def _events() -> list[dict]:
    return [
        {
            "timestamp": "2026-11-19T10:00:00+00:00",
            "source": "auth.log",
            "event_type": "failed_login",
            "severity": "low",
            "description": "failure one",
            "source_ip": "203.0.113.45",
        },
        {
            "timestamp": "2026-11-19T10:05:00+00:00",
            "source": "auth.log",
            "event_type": "failed_login",
            "severity": "high",
            "description": "failure two",
            "source_ip": "203.0.113.46",
        },
        {
            "timestamp": "2026-11-19T10:10:00+00:00",
            "source": "auth.log",
            "event_type": "failed_login",
            "severity": "low",
            "description": "failure three",
            "source_ip": "198.51.100.7",
        },
    ]


def test_source_cidr_filter_boundaries(tmp_initialised_db: Path) -> None:
    save_events(_events(), tmp_initialised_db)
    page = query_events({"source_cidr": "203.0.113.0/24"}, db_path=tmp_initialised_db)
    assert len(page["items"]) == 2
    assert (
        query_events({"source_cidr": "203.0.113.45/32"}, db_path=tmp_initialised_db)["items"][0][
            "source_ip"
        ]
        == "203.0.113.45"
    )
    assert (
        query_events({"source_cidr": "203.0.113.64/26"}, db_path=tmp_initialised_db)["items"] == []
    )


def test_in_incident_filter_and_total(tmp_initialised_db: Path) -> None:
    save_events(_events(), tmp_initialised_db)
    stamp = "2026-11-19T10:00:00+00:00"
    with closing(get_connection(tmp_initialised_db)) as connection, connection:
        connection.execute(
            "INSERT INTO incidents(correlation_key, title, first_seen, last_seen, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("demo-key", "Demo", stamp, stamp, stamp, stamp),
        )
        connection.execute(
            "INSERT INTO incident_events(incident_id, event_id, relation_reason, link_strength) "
            "VALUES (?, ?, ?, ?)",
            (1, 1, "shared source ip", "strong"),
        )
    page = query_events({"in_incident": True}, db_path=tmp_initialised_db)
    assert len(page["items"]) == 1
    assert page["total"] == 1
    assert query_events({}, db_path=tmp_initialised_db)["total"] == 3


def test_time_series_by_severity_is_zero_filled(tmp_initialised_db: Path) -> None:
    save_events(_events(), tmp_initialised_db)
    series = event_time_series_by_severity(
        {
            "since": "2026-11-19T10:00:00+00:00",
            "until": "2026-11-19T11:00:00+00:00",
        },
        bucket="hour",
        zero_fill=True,
        db_path=tmp_initialised_db,
    )
    assert series["2026-11-19T10:00:00+00:00"] == {"low": 2, "high": 1}
    assert series["2026-11-19T11:00:00+00:00"] == {}


def test_bulk_export_is_filtered_and_bounded(tmp_initialised_db: Path) -> None:
    save_events(_events(), tmp_initialised_db)
    rows = query_events_bulk({"severity": ["low"]}, limit=1, db_path=tmp_initialised_db)
    assert len(rows) == 1
    assert rows[0]["severity"] == "low"
    with pytest.raises(ValueError):
        query_events_bulk({}, limit=100_001, db_path=tmp_initialised_db)
