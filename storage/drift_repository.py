"""Monitored paths and snapshots persistence (Phase 9)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import load_settings
from core.drift_detection import (
    CATEGORIES,
    KINDS,
    SENSITIVITIES,
    PathSpec,
    validate_path,
)
from core.timeutil import utc_now
from storage.database import get_connection

__all__ = [
    "delete_monitored_path",
    "list_snapshot_history",
    "update_monitored_path",
    "MonitoredPath",
    "accept_baseline",
    "add_monitored_path",
    "get_baseline_snapshot",
    "get_previous_snapshot",
    "list_monitored_paths",
    "reset_all_monitored_paths",
    "reset_monitored_path",
    "save_snapshot",
    "seed_monitored_paths",
]

SHADOW_PATHS = frozenset({"/etc/shadow", "/etc/gshadow"})
MAX_PATHS = 200

_DEFAULT_PATHS: tuple[dict[str, Any], ...] = (
    {"path": "/etc/passwd", "kind": "file", "sensitivity": "high", "category": "system_account"},
    {"path": "/etc/group", "kind": "file", "sensitivity": "medium", "category": "system_account"},
    {
        "path": "/etc/shadow",
        "kind": "file",
        "sensitivity": "critical",
        "category": "system_account",
        "metadata_only": True,
    },
    {
        "path": "/etc/gshadow",
        "kind": "file",
        "sensitivity": "critical",
        "category": "system_account",
        "metadata_only": True,
    },
    {"path": "/etc/sudoers", "kind": "file", "sensitivity": "critical", "category": "sudo"},
    {"path": "/etc/sudoers.d", "kind": "dir", "sensitivity": "critical", "category": "sudo"},
    {"path": "/etc/ssh/sshd_config", "kind": "file", "sensitivity": "high", "category": "ssh"},
    {"path": "/etc/ssh/sshd_config.d", "kind": "dir", "sensitivity": "high", "category": "ssh"},
    {"path": "/etc/crontab", "kind": "file", "sensitivity": "high", "category": "cron"},
    {"path": "/etc/cron.d", "kind": "dir", "sensitivity": "high", "category": "cron"},
    {"path": "/etc/cron.daily", "kind": "dir", "sensitivity": "high", "category": "cron"},
    {"path": "/etc/cron.hourly", "kind": "dir", "sensitivity": "high", "category": "cron"},
    {"path": "/var/spool/cron/crontabs", "kind": "dir", "sensitivity": "high", "category": "cron"},
    {"path": "/etc/systemd/system", "kind": "dir", "sensitivity": "high", "category": "systemd"},
    {
        "path": "/etc/ld.so.preload",
        "kind": "file",
        "sensitivity": "critical",
        "category": "ld_preload",
    },
    {"path": "/etc/profile.d", "kind": "dir", "sensitivity": "medium", "category": "shell_profile"},
    {
        "path": "/root/.ssh/authorized_keys",
        "kind": "authorized_keys",
        "sensitivity": "critical",
        "category": "authorized_keys",
    },
)


@dataclass(frozen=True)
class MonitoredPath:
    id: int
    path: str
    kind: str
    sensitivity: str
    category: str
    metadata_only: bool
    enabled: bool
    recursive: bool
    max_entries: int
    builtin: bool = False
    default_definition_json: str = "{}"

    def as_spec(self) -> PathSpec:
        return PathSpec(
            id=self.id,
            path=self.path,
            kind=self.kind,
            sensitivity=self.sensitivity,
            category=self.category,
            metadata_only=self.metadata_only,
            enabled=self.enabled,
            recursive=self.recursive,
            max_entries=self.max_entries,
        )


def _row_to_path(row: Any) -> MonitoredPath:
    return MonitoredPath(
        id=row["id"],
        path=row["path"],
        kind=row["kind"],
        sensitivity=row["sensitivity"],
        category=row["category"],
        metadata_only=bool(row["metadata_only"]),
        enabled=bool(row["enabled"]),
        recursive=bool(row["recursive"]),
        max_entries=row["max_entries"],
        builtin=bool(row["builtin"]),
        default_definition_json=row["default_definition_json"],
    )


def _normalise(data: Mapping[str, Any], *, allow_custom_paths: bool) -> dict[str, Any]:
    path = validate_path(str(data["path"]), allow_custom_paths=allow_custom_paths)
    kind = data.get("kind", "file")
    sensitivity = data.get("sensitivity", "medium")
    category = data.get("category", "other")
    if kind not in KINDS:
        raise ValueError(f"invalid monitored path kind: {kind}")
    if sensitivity not in SENSITIVITIES:
        raise ValueError(f"invalid sensitivity: {sensitivity}")
    if category not in CATEGORIES:
        raise ValueError(f"invalid category: {category}")
    metadata_only = bool(data.get("metadata_only", False)) or path in SHADOW_PATHS
    return {
        "path": path,
        "kind": kind,
        "sensitivity": sensitivity,
        "category": category,
        "metadata_only": metadata_only,
        "enabled": bool(data.get("enabled", True)),
        "recursive": bool(data.get("recursive", False)),
        "max_entries": int(data.get("max_entries", 2000)),
    }


def _audit(
    connection: Any, actor: str, action: str, identifier: int, before: Any, after: Any
) -> None:
    connection.execute(
        "INSERT INTO audit_log(ts, actor, action, target_type, target_id, before_json, "
        "after_json, ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            utc_now().isoformat(),
            actor,
            action,
            "monitored_path",
            str(identifier),
            None if before is None else json.dumps(before, sort_keys=True),
            None if after is None else json.dumps(after, sort_keys=True),
            None,
        ),
    )


def seed_monitored_paths(db_path: str | Path | None = None) -> dict[str, int]:
    inserted = 0
    with closing(get_connection(db_path)) as connection, connection:
        for index, definition in enumerate(_DEFAULT_PATHS):
            values = _normalise(definition, allow_custom_paths=True)
            cursor = connection.execute(
                "INSERT OR IGNORE INTO monitored_paths(path, kind, sensitivity, category, "
                "metadata_only, enabled, recursive, max_entries, builtin, "
                "default_definition_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (
                    values["path"],
                    values["kind"],
                    values["sensitivity"],
                    values["category"],
                    int(values["metadata_only"]),
                    int(values["enabled"]),
                    int(values["recursive"]),
                    values["max_entries"],
                    json.dumps({**values, "id": index + 1}, sort_keys=True),
                ),
            )
            inserted += cursor.rowcount
    return {"monitored_paths": inserted}


def add_monitored_path(
    data: Mapping[str, Any],
    actor: str,
    db_path: str | Path | None = None,
    *,
    allow_custom_paths: bool | None = None,
) -> int:
    if allow_custom_paths is None:
        allow_custom_paths = load_settings().drift.allow_custom_paths
    values = _normalise(data, allow_custom_paths=allow_custom_paths)
    with closing(get_connection(db_path)) as connection, connection:
        count = connection.execute("SELECT COUNT(*) FROM monitored_paths").fetchone()[0]
        if count >= MAX_PATHS:
            raise ValueError(f"at most {MAX_PATHS} monitored paths are allowed")
        cursor = connection.execute(
            "INSERT INTO monitored_paths(path, kind, sensitivity, category, metadata_only, "
            "enabled, recursive, max_entries, builtin, default_definition_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (
                values["path"],
                values["kind"],
                values["sensitivity"],
                values["category"],
                int(values["metadata_only"]),
                int(values["enabled"]),
                int(values["recursive"]),
                values["max_entries"],
                json.dumps(values, sort_keys=True),
            ),
        )
        identifier = int(cursor.lastrowid or 0)
        _audit(connection, actor, "drift.path.add", identifier, None, values)
    return identifier


def list_monitored_paths(
    db_path: str | Path | None = None, *, enabled_only: bool = False
) -> list[MonitoredPath]:
    statement = "SELECT * FROM monitored_paths"
    if enabled_only:
        statement += " WHERE enabled = 1"
    statement += " ORDER BY id"
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(statement).fetchall()
    return [_row_to_path(row) for row in rows]


def reset_monitored_path(identifier: int, actor: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM monitored_paths WHERE id = ?", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown monitored path: {identifier}")
        default = json.loads(row["default_definition_json"] or "{}")
        if not default:
            raise ValueError("custom monitored paths have no default to reset to")
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "UPDATE monitored_paths SET kind = ?, sensitivity = ?, category = ?, "
            "metadata_only = ?, enabled = ?, recursive = ?, max_entries = ? WHERE id = ?",
            (
                default["kind"],
                default["sensitivity"],
                default["category"],
                int(default["metadata_only"]),
                int(default["enabled"]),
                int(default["recursive"]),
                default["max_entries"],
                identifier,
            ),
        )
        _audit(connection, actor, "drift.path.reset", identifier, dict(row), default)


def reset_all_monitored_paths(actor: str, db_path: str | Path | None = None) -> int:
    builtins = [item.id for item in list_monitored_paths(db_path) if item.builtin]
    for identifier in builtins:
        reset_monitored_path(identifier, actor, db_path)
    return len(builtins)


def _row_to_snapshot(row: Any) -> dict[str, Any]:
    return {
        "path": row["path"],
        "exists": bool(row["exists_flag"]),
        "sha256": row["sha256"],
        "owner": row["owner"],
        "group": row["group_name"],
        "mode": row["mode"],
        "mtime": row["mtime"],
        "size": row["size"],
        "is_symlink": bool((json.loads(row["extra_json"] or "{}")).get("is_symlink", False)),
        "extra": json.loads(row["extra_json"] or "{}"),
        "captured_at": row["captured_at"],
        "is_baseline": bool(row["is_baseline"]),
    }


def save_snapshot(
    snapshot: Mapping[str, Any],
    *,
    is_baseline: bool = False,
    db_path: str | Path | None = None,
) -> int:
    extra = dict(snapshot.get("extra") or {})
    extra["is_symlink"] = bool(snapshot.get("is_symlink"))
    with closing(get_connection(db_path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO file_snapshots(path, exists_flag, sha256, owner, group_name, mode, "
            "mtime, size, extra_json, captured_at, is_baseline) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot["path"],
                int(bool(snapshot.get("exists"))),
                snapshot.get("sha256"),
                snapshot.get("owner"),
                snapshot.get("group"),
                snapshot.get("mode"),
                snapshot.get("mtime"),
                snapshot.get("size"),
                json.dumps(extra, sort_keys=True, default=str),
                snapshot.get("captured_at") or utc_now().isoformat(),
                int(is_baseline),
            ),
        )
        return int(cursor.lastrowid or 0)


def get_previous_snapshot(path: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM file_snapshots WHERE path = ? ORDER BY id DESC LIMIT 1", (path,)
        ).fetchone()
    return None if row is None else _row_to_snapshot(row)


def update_monitored_path(
    identifier: int, changes: dict[str, Any], actor: str, db_path: str | Path | None = None
) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "UPDATE monitored_paths SET enabled = ?, sensitivity = ?, category = ? WHERE id = ?",
            (
                int(changes.get("enabled", True)),
                changes.get("sensitivity", "medium"),
                changes.get("category", "other"),
                identifier,
            ),
        )
        _audit(connection, actor, "drift.path.update", identifier, None, changes)


def delete_monitored_path(identifier: int, actor: str, db_path: str | Path | None = None) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("DELETE FROM monitored_paths WHERE id = ?", (identifier,))
        _audit(connection, actor, "drift.path.delete", identifier, None, {"deleted": identifier})


def list_snapshot_history(
    path: str, limit: int = 100, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM file_snapshots WHERE path = ? ORDER BY id DESC LIMIT ?",
            (path, limit),
        ).fetchall()
    return [_row_to_snapshot(row) for row in rows]


def get_baseline_snapshot(path: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM file_snapshots WHERE path = ? AND is_baseline = 1 "
            "ORDER BY id DESC LIMIT 1",
            (path,),
        ).fetchone()
    return None if row is None else _row_to_snapshot(row)


def accept_baseline(
    identifier: int, actor: str, reason: str, db_path: str | Path | None = None
) -> None:
    if not reason or not reason.strip():
        raise ValueError("a reason is required to accept a baseline")
    path = next(
        (item.path for item in list_monitored_paths(db_path) if item.id == identifier), None
    )
    if path is None:
        raise ValueError(f"unknown monitored path: {identifier}")
    current = get_previous_snapshot(path, db_path)
    if current is None:
        raise ValueError(f"no snapshot to accept for {path}")
    save_snapshot(current, is_baseline=True, db_path=db_path)
    with closing(get_connection(db_path)) as connection, connection:
        _audit(
            connection,
            actor,
            "drift.baseline_accepted",
            identifier,
            None,
            {"path": path, "reason": reason.strip()},
        )
