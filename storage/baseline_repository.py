"""Baseline summary persistence and chart series (Phase 8)."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any

from core.baseline import Baseline
from core.timeutil import utc_now
from storage.database import get_connection

__all__ = ["get_baseline_series", "list_baselines", "save_baseline"]


def _row_to_baseline(row: Any) -> Baseline:
    return Baseline(
        metric=row["metric"],
        subject=row["subject"],
        window_start=row["window_start"],
        window_end=row["window_end"],
        mean=row["mean"],
        stddev=row["stddev"],
        sample_count=row["sample_count"],
        maximum=row["mean"],
        p95=row["mean"],
        maturity="mature",
        reason="",
    )


def save_baseline(baseline: Baseline, db_path: str | Path | None = None) -> bool:
    """Upsert one summary row per metric/subject/day; returns whether it was new."""
    with closing(get_connection(db_path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO baselines(metric, subject, bucket, window_start, window_end, "
            "mean, stddev, sample_count, buckets_json, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(metric, subject, bucket) DO UPDATE SET "
            "window_start = excluded.window_start, window_end = excluded.window_end, "
            "mean = excluded.mean, stddev = excluded.stddev, "
            "sample_count = excluded.sample_count, buckets_json = excluded.buckets_json, "
            "computed_at = excluded.computed_at",
            (
                baseline.metric,
                baseline.subject,
                baseline.window_end[:10],
                baseline.window_start,
                baseline.window_end,
                baseline.mean,
                baseline.stddev,
                baseline.sample_count,
                json.dumps(list(baseline.buckets), sort_keys=True),
                utc_now().isoformat(),
            ),
        )
        return cursor.rowcount > 0


def list_baselines(db_path: str | Path | None = None) -> list[Baseline]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM baselines ORDER BY metric, subject, window_end"
        ).fetchall()
    return [_row_to_baseline(row) for row in rows]


def get_baseline_series(
    metric: str,
    subject: str,
    *,
    since: str | None = None,
    z: float = 3.0,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return baseline bands for charting, optionally since an ISO timestamp."""
    statement = "SELECT * FROM baselines WHERE metric = ? AND subject = ?"
    parameters: list[Any] = [metric, subject]
    if since:
        statement += " AND window_end >= ?"
        parameters.append(since)
    statement += " ORDER BY window_end"
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement, parameters).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        band = {
            "mean": row["mean"],
            "stddev": row["stddev"],
            "upper": row["mean"] + z * row["stddev"],
            "lower": row["mean"] - z * row["stddev"],
            "sample_count": row["sample_count"],
        }
        buckets = json.loads(row["buckets_json"] or "[]")
        if buckets:
            result.extend(
                {**band, "timestamp": item["timestamp"], "value": item["value"]} for item in buckets
            )
        else:
            result.append({**band, "timestamp": row["window_end"], "value": row["mean"]})
    return result
