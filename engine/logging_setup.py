"""JSON logging with redaction of secret-looking fields."""

from __future__ import annotations

import json
import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, TextIO

__all__ = ["JsonFormatter", "RedactionFilter", "setup_logging"]

_SECRET_KEY = re.compile(r"password|secret|token|authorization|cookie", re.IGNORECASE)


class RedactionFilter(logging.Filter):
    """Remove values belonging to secret-looking format labels or extra keys."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__):
            if _SECRET_KEY.search(key):
                setattr(record, key, "***")
        args = record.args
        if isinstance(record.msg, str) and isinstance(args, tuple) and "%s" in record.msg:
            labels = re.findall(r"(\w+)=", record.msg)
            redacted = tuple(
                "***" if index < len(labels) and _SECRET_KEY.search(labels[index]) else value
                for index, value in enumerate(args)
            )
            record.args = redacted
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in ("component", "request_id", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging(
    *, stream: TextIO | None = None, level: int = logging.INFO, log_dir: str | Path | None = None
) -> logging.Logger:
    logger = logging.getLogger("sentinel")
    logger.setLevel(level)
    logger.handlers.clear()
    formatter = JsonFormatter()
    filt = RedactionFilter()
    console = logging.StreamHandler(stream or sys.stderr)
    console.setFormatter(formatter)
    console.addFilter(filt)
    logger.addHandler(console)
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            str(Path(log_dir) / "sentinel.log"), maxBytes=10 * 1024 * 1024, backupCount=5
        )
        handler.setFormatter(formatter)
        handler.addFilter(filt)
        logger.addHandler(handler)
    return logger
