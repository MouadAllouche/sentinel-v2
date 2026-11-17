"""Time helpers. Pure apart from ``utc_now`` and local-timezone discovery.

All stored timestamps are UTC-aware ISO 8601 with a ``+00:00`` offset. Naive
input is interpreted in the configured local timezone by the caller; the
``tz`` argument lets callers inject that zone so this module stays testable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo

__all__ = [
    "floor_hour",
    "parse_ts",
    "to_utc_iso",
    "utc_now",
    "window_bounds",
]


def utc_now() -> datetime:
    """Return a UTC-aware datetime for "now" (the single clock entry point)."""
    return datetime.now(UTC)


def _local_tzinfo() -> tzinfo:
    """Discover the host's current local offset via the single clock entry point.

    ``utc_now().astimezone()`` converts to local time without a second clock read.
    Monkeypatchable in tests.
    """
    discovered = utc_now().astimezone().tzinfo
    if discovered is None:  # pragma: no cover - astimezone always attaches one
        return UTC
    return discovered


def _coerce_datetime(value: str | datetime, *, year: int | None, now: datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string or datetime")
    text = value.strip()
    if not text:
        raise ValueError("timestamp must not be empty")
    iso_candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(iso_candidate)
    except ValueError:
        pass
    try:
        stamp = datetime.strptime(" ".join(text.split()), "%b %d %H:%M:%S")
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc
    if year is None:
        reference = now if now is not None else utc_now()
        year = reference.year
        if (stamp.replace(year=year) - reference.replace(tzinfo=None)).days > 1:
            year -= 1
    try:
        return stamp.replace(year=year)
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc


def _resolve_tz(tz: tzinfo | None, assume_local: bool) -> tzinfo:
    if tz is not None:
        return tz
    return _local_tzinfo() if assume_local else UTC


def to_utc_iso(
    value: str | datetime,
    assume_local: bool = True,
    *,
    year: int | None = None,
    tz: tzinfo | None = None,
    now: datetime | None = None,
) -> str:
    """Convert an ISO or syslog timestamp to a UTC-aware ISO string.

    ``assume_local`` controls naive input; an explicit ``tz`` always wins.
    ``year`` (or the injectable ``now``) supplies the year for syslog prefixes.
    """
    parsed = _coerce_datetime(value, year=year, now=now)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=_resolve_tz(tz, assume_local))
    return parsed.astimezone(UTC).isoformat()


def parse_ts(value: str, assume_local: bool = True) -> datetime:
    """Parse an ISO timestamp into a UTC-aware datetime."""
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    text = value.strip()
    iso_candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=_resolve_tz(None, assume_local))
    return parsed.astimezone(UTC)


def floor_hour(value: datetime) -> datetime:
    """Truncate a datetime to the start of its hour, preserving its timezone."""
    return value.replace(minute=0, second=0, microsecond=0)


def window_bounds(
    end: datetime, window_seconds: int, *, assume_local: bool = True
) -> tuple[datetime, datetime]:
    """Return ``(start, end)`` for a window of the given length in seconds.

    Membership is defined by callers as ``(start, end]`` (Phase 5 semantics).
    """
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    if end.tzinfo is None or end.utcoffset() is None:
        end = end.replace(tzinfo=_resolve_tz(None, assume_local))
    return end - timedelta(seconds=window_seconds), end
