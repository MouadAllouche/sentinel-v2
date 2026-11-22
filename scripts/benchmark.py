"""Real performance measurements for the simulator evaluation (not part of pytest).

Run via ``python cli.py simulate metrics`` or directly for a single measurement
set. Every number is measured on the machine where this module runs.
"""

from __future__ import annotations

import os
import platform
import statistics
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from collectors.logs import parse_auth_line
from core.rules.engine import evaluate_rules
from core.rules.models import validate_rule
from storage.auth_repository import create_user
from storage.database import get_connection, init_db
from storage.repositories import save_events

ROOT = Path(__file__).resolve().parents[1]
EVENT_COUNT = 200_000
SIZE_COUNT = 100_000
API_CALLS = 100


def _environment() -> dict[str, str]:
    return {
        "machine": platform.platform(),
        "python": f"Python {platform.python_version()} ({platform.python_implementation()})",
        "cpu": (
            f"{platform.machine()}, {os.cpu_count()} logical CPUs, "
            f"{platform.processor() or 'model not reported'}"
        ),
        "memory": "reported by psutil.virtual_memory().total in the benchmark run",
    }


def _raw_events(count: int, start: datetime) -> list[dict[str, Any]]:
    """Synthetic auth.log lines parsed by the real collector parser."""
    events: list[dict[str, Any]] = []
    for index in range(count):
        stamp = start + timedelta(seconds=index)
        line = (
            f"{stamp.isoformat()} sshd[1]: Failed password for user{index % 97} "
            "from 203.0.113.45 port 2200"
        )
        parsed = parse_auth_line(line)
        if parsed is not None:
            events.append(parsed)
    return events


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def run_benchmarks(workdir: Path) -> dict[str, Any]:
    import psutil

    env = _environment()
    env["memory"] = f"{psutil.virtual_memory().total} bytes total (psutil.virtual_memory())"
    workdir.mkdir(parents=True, exist_ok=True)

    # Ingestion rate: 100k real parser outputs through save_events.
    ingest_db = workdir / "ingest.db"
    init_db(ingest_db)
    ingest_events = _raw_events(SIZE_COUNT, datetime(2026, 1, 1, tzinfo=UTC))
    started = time.perf_counter()
    for offset in range(0, len(ingest_events), 10_000):
        save_events(ingest_events[offset : offset + 10_000], ingest_db)
    ingest_seconds = time.perf_counter() - started
    ingestion_rate = len(ingest_events) / ingest_seconds

    # Database size for 100k events.
    size_100k = ingest_db.stat().st_size

    # Rule evaluation over 200k events.
    from core.rules.defaults import DEFAULT_RULES

    rule = validate_rule(
        next(
            definition for definition in DEFAULT_RULES if definition["id"] == "ssh-bruteforce-by-ip"
        )
    )[0]
    evaluation_events = ingest_events + _raw_events(
        EVENT_COUNT - len(ingest_events), datetime(2026, 1, 2, tzinfo=UTC)
    )
    started = time.perf_counter()
    evaluate_rules([rule], evaluation_events, datetime(2026, 1, 3, tzinfo=UTC))
    evaluation_seconds = time.perf_counter() - started

    # API list latency over 200k events, 100 calls each endpoint.
    api_db = workdir / "api.db"
    init_db(api_db)
    create_user("bench-admin", "benchmark-password-123", "admin", api_db)
    for offset in range(0, len(evaluation_events), 10_000):
        save_events(evaluation_events[offset : offset + 10_000], api_db)
    os.environ["SENTINEL_SESSION_KEY"] = "benchmark-session-key-0123456789abcdef"
    from api.main import create_app

    app = create_app(db_path=str(api_db))
    api_latency: dict[str, dict[str, float]] = {}
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "bench-admin", "password": "benchmark-password-123"},
        )
        if login.status_code != 200:
            raise RuntimeError(f"benchmark login failed: {login.text}")
        for path in ("/api/events", "/api/incidents"):
            samples: list[float] = []
            for _ in range(API_CALLS):
                started = time.perf_counter()
                response = client.get(path, params={"limit": 50})
                samples.append((time.perf_counter() - started) * 1000)
                if response.status_code != 200:
                    raise RuntimeError(f"benchmark API call failed: {response.text}")
            api_latency[path] = {
                "median_ms": statistics.median(samples),
                "p95_ms": _percentile(samples, 0.95),
                "calls": len(samples),
            }

    # Sanity check: all event data was actually stored.
    with get_connection(api_db) as connection:
        stored = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    return {
        "environment": env,
        "measurements": {
            "ingestion_events_per_second": round(ingestion_rate, 1),
            "ingestion_seconds_for_100k": round(ingest_seconds, 3),
            "rule_evaluation_200k_seconds": round(evaluation_seconds, 3),
            "api_calls_per_endpoint": API_CALLS,
            "api_events_median_ms": round(api_latency["/api/events"]["median_ms"], 2),
            "api_events_p95_ms": round(api_latency["/api/events"]["p95_ms"], 2),
            "api_incidents_median_ms": round(api_latency["/api/incidents"]["median_ms"], 2),
            "api_incidents_p95_ms": round(api_latency["/api/incidents"]["p95_ms"], 2),
            "database_bytes_per_100k_events": size_100k,
            "events_stored_for_api_benchmark": stored,
        },
    }
