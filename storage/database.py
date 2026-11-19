"""SQLite connection setup and migration application.

This is the only module that owns connection pragmas. All SQL in ``storage/``
is parameterised; database paths are injectable so tests never use the real DB.
"""

from __future__ import annotations

import ipaddress
import sqlite3
from contextlib import closing
from pathlib import Path

from core.config import Settings, load_settings
from core.timeutil import utc_now
from storage.migrations import MIGRATIONS, _record_version, current_version

__all__ = ["default_db_path", "get_connection", "init_db"]


def _ip_in_cidr(address: str | None, network: str) -> int:
    """SQL helper for CIDR filters; invalid input never matches."""
    if not address:
        return 0
    try:
        return int(ipaddress.ip_address(address) in ipaddress.ip_network(network, strict=False))
    except ValueError:
        return 0


def default_db_path(settings: Settings | None = None) -> Path:
    """Return the configured database path, anchored by ``core.config``."""
    return (settings or load_settings()).paths.database


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a WAL connection with Sentinel's required pragmas."""
    path = default_db_path() if db_path is None else Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=5)
    connection.row_factory = sqlite3.Row
    connection.create_function("ip_in_cidr", 2, _ip_in_cidr)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def init_db(db_path: str | Path | None = None, *, now: str | None = None) -> None:
    """Apply all pending migrations, each in its own short transaction."""
    applied_at = now or utc_now().isoformat()
    with closing(get_connection(db_path)) as connection:
        version = current_version(connection)
        for number, migration in enumerate(MIGRATIONS, start=1):
            if version >= number:
                continue
            # Explicit transaction: SQLite does not implicitly wrap DDL in one.
            connection.execute("BEGIN")
            try:
                migration(connection)
                _record_version(connection, number, applied_at)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            version = number
