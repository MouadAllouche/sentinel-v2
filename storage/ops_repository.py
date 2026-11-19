"""Operational read helpers for the API layer."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from storage.database import get_connection

__all__ = ["list_changes", "list_collector_runs", "list_cycle_runs"]


def _recent(
    table: str, column: str, limit: int, db_path: str | Path | None
) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM " + table + " ORDER BY " + column + " DESC LIMIT ?",  # noqa: S608
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_collector_runs(
    limit: int = 100, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    return _recent("collector_runs", "id", limit, db_path)


def list_cycle_runs(limit: int = 100, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    return _recent("cycle_runs", "id", limit, db_path)


def list_changes(
    after: int, limit: int = 100, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM changes WHERE id > ? ORDER BY id LIMIT ?", (after, limit)
        ).fetchall()
    return [dict(row) for row in rows]
