"""Users, sessions and saved filters persistence (Phase 12)."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from typing import Any

from core.auth import hash_password, validate_password
from core.timeutil import utc_now
from storage.database import get_connection

__all__ = [
    "add_failed_login",
    "create_saved_filter",
    "create_session",
    "create_user",
    "delete_saved_filter",
    "delete_session",
    "get_session",
    "get_user",
    "get_user_by_name",
    "list_saved_filters",
    "list_sessions",
    "list_users",
    "record_failed_login",
    "reset_login_failures",
    "revoke_user_sessions",
    "set_password",
    "set_user_disabled",
    "touch_session",
    "update_role",
]


def _audit(
    connection: Any,
    actor: str,
    action: str,
    identifier: Any,
    after: Any,
    ip: str | None = None,
) -> None:
    connection.execute(
        "INSERT INTO audit_log(ts, actor, action, target_type, target_id, before_json, "
        "after_json, ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            utc_now().isoformat(),
            actor,
            action,
            "user",
            str(identifier),
            None,
            json.dumps(after, sort_keys=True, default=str),
            ip,
        ),
    )


def create_user(
    username: str,
    password: str,
    role: str,
    db_path: str | Path | None = None,
    *,
    actor: str = "system",
) -> int:
    if role not in {"admin", "viewer"}:
        raise ValueError("role must be admin or viewer")
    encoded = hash_password(password)
    with closing(get_connection(db_path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO users(username, password_hash, role, disabled, failed_logins, "
            "created_at) VALUES (?, ?, ?, 0, 0, ?)",
            (username, encoded, role, utc_now().isoformat()),
        )
        identifier = int(cursor.lastrowid or 0)
        _audit(
            connection, "system", "user.create", identifier, {"username": username, "role": role}
        )
    return identifier


def _row(row: Any) -> dict[str, Any]:
    return dict(row)


def get_user(identifier: int, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (identifier,)).fetchone()
    return None if row is None else _row(row)


def get_user_by_name(username: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return None if row is None else _row(row)


def list_users(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [_row(row) for row in rows]


def set_user_disabled(
    identifier: int,
    disabled: bool,
    db_path: str | Path | None = None,
    *,
    actor: str = "system",
) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "UPDATE users SET disabled = ? WHERE id = ?", (int(disabled), identifier)
        )
        _audit(connection, actor, "user.disabled", identifier, {"disabled": disabled})
    if disabled:
        revoke_user_sessions(identifier, db_path)


def update_role(
    identifier: int,
    role: str,
    db_path: str | Path | None = None,
    *,
    actor: str = "system",
) -> None:
    if role not in {"admin", "viewer"}:
        raise ValueError("role must be admin or viewer")
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("UPDATE users SET role = ? WHERE id = ?", (role, identifier))
        _audit(connection, actor, "user.role", identifier, {"role": role})


def set_password(
    identifier: int,
    password: str,
    db_path: str | Path | None = None,
    *,
    actor: str = "system",
    revoke: bool = True,
) -> None:
    validate_password(password)
    encoded = hash_password(password)
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "UPDATE users SET password_hash = ?, failed_logins = 0, locked_until = NULL "
            "WHERE id = ?",
            (encoded, identifier),
        )
        _audit(connection, actor, "user.password", identifier, {"password": "changed"})
    if revoke:
        revoke_user_sessions(identifier, db_path)


def update_password_hash(identifier: int, encoded: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (encoded, identifier))


def add_failed_login(
    username: str,
    ip: str,
    db_path: str | Path | None = None,
    *,
    actor: str = "system",
) -> None:
    """Increment per-user and per-IP failures; lock with exponential repeats."""
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "UPDATE users SET failed_logins = failed_logins + 1 WHERE username = ?", (username,)
        )
        connection.execute(
            "INSERT INTO login_failures(ip, username, count, first_at) VALUES (?, ?, 1, ?) "
            "ON CONFLICT(ip, username) DO UPDATE SET count = count + 1",
            (ip, username, utc_now().isoformat()),
        )
        row = connection.execute(
            "SELECT failed_logins, lock_count FROM users WHERE username = ?", (username,)
        ).fetchone()
        ip_row = connection.execute(
            "SELECT count FROM login_failures WHERE ip = ? AND username = ?", (ip, username)
        ).fetchone()
        if row and (row["failed_logins"] >= 5 or (ip_row and ip_row["count"] >= 5)):
            minutes = 15 * (2 ** int(row["lock_count"] or 0))
            connection.execute(
                "UPDATE users SET locked_until = ?, failed_logins = 0, lock_count = lock_count + 1 "
                "WHERE username = ?",
                ((utc_now() + timedelta(minutes=minutes)).isoformat(), username),
            )
        _audit(connection, actor, "auth.login_failed", username, {"ip": ip})


def record_failed_login(username: str, ip: str, db_path: str | Path | None = None) -> None:
    """Compatibility wrapper used by unit tests."""
    add_failed_login(username, ip, db_path)


def reset_login_failures(username: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "UPDATE users SET failed_logins = 0, locked_until = NULL WHERE username = ?",
            (username,),
        )


def create_session(
    identifier: str,
    user_id: int,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    expires_at: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    now = utc_now()
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO sessions(id_hash, user_id, created_at, last_seen, expires_at, ip, "
            "user_agent) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                identifier,
                user_id,
                now.isoformat(),
                now.isoformat(),
                expires_at or (now + timedelta(hours=12)).isoformat(),
                ip,
                user_agent,
            ),
        )


def get_session(identifier: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM sessions WHERE id_hash = ?", (identifier,)
        ).fetchone()
    return None if row is None else _row(row)


def touch_session(identifier: str, last_seen: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "UPDATE sessions SET last_seen = ? WHERE id_hash = ?", (last_seen, identifier)
        )


def delete_session(identifier: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("DELETE FROM sessions WHERE id_hash = ?", (identifier,))


def list_sessions(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute("SELECT * FROM sessions ORDER BY created_at").fetchall()
    return [_row(row) for row in rows]


def revoke_user_sessions(user_id: int, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def create_saved_filter(
    user_id: int, name: str, page: str, query: dict[str, Any], db_path: str | Path | None = None
) -> int:
    with closing(get_connection(db_path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO saved_filters(user_id, name, page, query_json) VALUES (?, ?, ?, ?)",
            (user_id, name, page, json.dumps(query, sort_keys=True)),
        )
        return int(cursor.lastrowid or 0)


def list_saved_filters(user_id: int, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM saved_filters WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
    return [{**_row(row), "query": json.loads(row["query_json"])} for row in rows]


def delete_saved_filter(identifier: int, user_id: int, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "DELETE FROM saved_filters WHERE id = ? AND user_id = ?", (identifier, user_id)
        )
        _audit(connection, str(user_id), "filter.delete", identifier, {"user_id": user_id})
