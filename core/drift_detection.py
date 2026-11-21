"""Pure drift comparison and path validation. No filesystem, clock or I/O."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

__all__ = [
    "Change",
    "PathSpec",
    "compare_snapshots",
    "describe_changes",
    "flags_for",
    "validate_path",
]

KINDS = frozenset({"file", "dir", "authorized_keys"})
SENSITIVITIES = frozenset({"low", "medium", "high", "critical"})
CATEGORIES = frozenset(
    {
        "system_account",
        "ssh",
        "sudo",
        "cron",
        "systemd",
        "authorized_keys",
        "ld_preload",
        "shell_profile",
        "other",
    }
)
DEFAULT_ALLOWED_PREFIXES = ("/etc", "/var/spool/cron", "/root", "/home", "/usr/local", "/opt")


@dataclass(frozen=True)
class PathSpec:
    id: int | None
    path: str
    kind: str
    sensitivity: str
    category: str
    metadata_only: bool = False
    enabled: bool = True
    recursive: bool = False
    max_entries: int = 2000


@dataclass(frozen=True)
class Change:
    field: str
    old: Any
    new: Any


def validate_path(
    path: str,
    *,
    allow_custom_paths: bool = False,
    allowed_prefixes: tuple[str, ...] = DEFAULT_ALLOWED_PREFIXES,
) -> str:
    """Require a normalised absolute path within the allowed prefixes."""
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("path must be absolute")
    if ".." in PathParts(path) or os.path.normpath(path) != path:
        raise ValueError("path must be normalised and contain no '..'")
    if not allow_custom_paths and not any(
        path == prefix or path.startswith(prefix + "/") for prefix in allowed_prefixes
    ):
        raise ValueError(f"path outside allowed prefixes: {path}")
    return path


def PathParts(path: str) -> list[str]:  # noqa: N802 - named like pathlib.PurePath.parts
    return [part for part in path.split("/") if part]


def _mode(mode: Any) -> int:
    try:
        return int(str(mode), 8)
    except (TypeError, ValueError):
        return 0


def compare_snapshots(
    previous: dict[str, Any], current: dict[str, Any], spec: PathSpec
) -> list[Change]:
    """Return exactly what changed between two snapshots."""
    changes: list[Change] = []
    if bool(previous.get("exists")) != bool(current.get("exists")):
        changes.append(Change("exists", previous.get("exists"), current.get("exists")))
    if not previous.get("exists") or not current.get("exists"):
        return changes
    for field in ("sha256", "owner", "group", "mode", "mtime", "size", "is_symlink"):
        if previous.get(field) != current.get(field):
            changes.append(Change(field, previous.get(field), current.get(field)))

    if spec.kind == "dir":
        before = {item["name"]: item for item in (previous.get("extra") or {}).get("entries", [])}
        after = {item["name"]: item for item in (current.get("extra") or {}).get("entries", [])}
        added = [after[name] for name in sorted(set(after) - set(before))]
        removed = [before[name] for name in sorted(set(before) - set(after))]
        modified: list[dict[str, Any]] = []
        for name in sorted(set(before) & set(after)):
            fields = [
                key
                for key in ("mode", "owner", "group", "size", "mtime", "sha256")
                if before[name].get(key) != after[name].get(key)
            ]
            if fields:
                modified.append({"name": name, "fields": fields})
        if added:
            changes.append(Change("entries_added", [], added))
        if removed:
            changes.append(Change("entries_removed", [], removed))
        if modified:
            changes.append(Change("entries_modified", [], modified))

    if spec.kind == "authorized_keys":
        before_f = set((previous.get("extra") or {}).get("fingerprints", []))
        after_f = set((current.get("extra") or {}).get("fingerprints", []))
        if after_f - before_f:
            changes.append(Change("fingerprints_added", [], sorted(after_f - before_f)))
        if before_f - after_f:
            changes.append(Change("fingerprints_removed", [], sorted(before_f - after_f)))

    if previous.get("is_symlink") or current.get("is_symlink"):
        before_target = (previous.get("extra") or {}).get("link_target_scope")
        after_target = (current.get("extra") or {}).get("link_target_scope")
        if before_target != after_target:
            changes.append(Change("symlink_target_changed", before_target, after_target))
    return changes


def flags_for(
    previous: dict[str, Any], current: dict[str, Any], changes: list[Change]
) -> list[str]:
    """Compute security-relevant change flags from a comparison."""
    flags: list[str] = []
    old_mode, new_mode = _mode(previous.get("mode")), _mode(current.get("mode"))
    if new_mode & 0o002 and not old_mode & 0o002:
        flags.append("world_writable")
    if new_mode & 0o020 and not old_mode & 0o020:
        flags.append("group_writable_added")
    if new_mode & 0o004 and not old_mode & 0o004:
        flags.append("world_readable_added")
    if new_mode & 0o4000 and not old_mode & 0o4000:
        flags.append("setuid_added")
    if (
        previous.get("owner") == "root"
        and current.get("owner") not in (None, "root")
        and any(change.field == "owner" for change in changes)
    ):
        flags.append("owner_changed_to_nonroot")
    return flags


def describe_changes(
    changes: list[Change], spec: PathSpec, flags: list[str], only_mtime: bool
) -> list[str]:
    """Return exact, content-free human descriptions of each change."""
    descriptions: list[str] = []
    for change in changes:
        if change.field == "exists":
            descriptions.append(f"{spec.path} {'added' if change.new else 'removed'}")
        elif change.field == "mode":
            descriptions.append(
                f"{spec.path} permissions changed from {change.old} to {change.new}"
            )
        elif change.field == "sha256":
            descriptions.append(f"{spec.path} content changed")
        elif change.field in {"owner", "group"}:
            descriptions.append(
                f"{spec.path} {change.field} changed from {change.old} to {change.new}"
            )
        elif change.field == "mtime":
            suffix = " (mtime only)" if only_mtime else ""
            descriptions.append(f"{spec.path} modification time changed{suffix}")
        elif change.field == "size":
            descriptions.append(f"{spec.path} size changed from {change.old} to {change.new}")
        elif change.field == "is_symlink":
            descriptions.append(f"{spec.path} symlink state changed")
        elif change.field == "entries_added":
            for entry in change.new:
                descriptions.append(
                    f"{spec.path}: new file '{entry['name']}' "
                    f"(mode {entry.get('mode')}, owner {entry.get('owner')})"
                )
        elif change.field == "entries_removed":
            for entry in change.new:
                descriptions.append(f"{spec.path}: file '{entry['name']}' removed")
        elif change.field == "entries_modified":
            for entry in change.new:
                descriptions.append(
                    f"{spec.path}: file '{entry['name']}' changed ({', '.join(entry['fields'])})"
                )
        elif change.field == "fingerprints_added":
            count = len(change.new)
            plural = "s" if count != 1 else ""
            descriptions.append(f"{spec.path}: {count} key{plural} added ({', '.join(change.new)})")
        elif change.field == "fingerprints_removed":
            count = len(change.new)
            plural = "s" if count != 1 else ""
            descriptions.append(
                f"{spec.path}: {count} key{plural} removed ({', '.join(change.new)})"
            )
        elif change.field == "symlink_target_changed":
            descriptions.append(f"{spec.path} symlink target changed")
    return descriptions
