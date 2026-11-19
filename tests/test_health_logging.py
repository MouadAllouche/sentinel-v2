"""Tests for JSON logging redaction and health states (Phase 11)."""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

from core.health import get_health
from engine.logging_setup import RedactionFilter, setup_logging

NOW_TEXT = "2026-11-15T12:00:00+00:00"


def test_redaction_filter_drops_secrets() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "password=%s token=%s safe=%s",
        ("hunter2", "abc123", "fine"),
        None,
    )
    RedactionFilter().filter(record)
    assert "hunter2" not in record.getMessage()
    assert "abc123" not in record.getMessage()
    assert "fine" in record.getMessage()


def test_setup_logging_emits_json(tmp_path: Path) -> None:
    stream = io.StringIO()
    logger = setup_logging(stream=stream, level=logging.INFO)
    logger.info("cycle.finished", extra={"component": "engine", "duration_ms": 12})
    payload = json.loads(stream.getvalue().strip())
    assert payload["event"] == "cycle.finished"
    assert payload["component"] == "engine"
    assert payload["duration_ms"] == 12


def test_health_states(tmp_initialised_db: Path) -> None:
    health = get_health(
        tmp_initialised_db, now=__import__("datetime").datetime.fromisoformat(NOW_TEXT)
    )
    assert health["status"] in {"ok", "degraded", "down"}
    assert "reasons" in health
    assert "db" in health
