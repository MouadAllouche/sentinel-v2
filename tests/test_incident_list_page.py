"""Storage tests for the incident list page used by Phase 15."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from storage.database import get_connection
from storage.incident_repository import list_incidents_page

STAMP = "2026-11-19T10:00:00+00:00"


def _seed(db: Path, count: int = 3) -> None:
    with closing(get_connection(db)) as connection, connection:
        for index in range(count):
            connection.execute(
                "INSERT INTO incidents(correlation_key, title, status, first_seen, last_seen, "
                "severity, risk_score, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"key-{index}",
                    f"Incident {index}",
                    "open" if index < 2 else "resolved",
                    STAMP,
                    STAMP,
                    "high",
                    10 * (index + 1),
                    STAMP,
                    STAMP,
                ),
            )


def test_page_is_sorted_and_cursor_bounded(tmp_initialised_db: Path) -> None:
    _seed(tmp_initialised_db)
    first = list_incidents_page({}, sort="risk", limit=2, db_path=tmp_initialised_db)
    assert [item["id"] for item in first["items"]] == [3, 2]
    assert first["next_cursor"]
    second = list_incidents_page(
        {}, sort="risk", limit=2, cursor=first["next_cursor"], db_path=tmp_initialised_db
    )
    assert [item["id"] for item in second["items"]] == [1]
    assert second["next_cursor"] is None


def test_filters_and_needs_attention(tmp_initialised_db: Path) -> None:
    _seed(tmp_initialised_db)
    page = list_incidents_page({"status": ["resolved"]}, db_path=tmp_initialised_db)
    assert [item["id"] for item in page["items"]] == [3]
    attention = list_incidents_page({"needs_attention": True}, db_path=tmp_initialised_db)
    assert {item["id"] for item in attention["items"]} == {1, 2}
