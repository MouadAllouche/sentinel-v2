"""Read-only filesystem helpers used by drift detection.

Only metadata and hashes are returned. File contents, key material and key
comments are never returned or stored. Symlinks are never traversed outside the
target directory.
"""

from __future__ import annotations

import base64
import binascii
import grp
import hashlib
import os
import pwd
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MAX_HASH_BYTES = 5 * 1024 * 1024


def _owner(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def _group(gid: int) -> str:
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return str(gid)


def _mtime(value: float) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def get_file_metadata(path: str | Path) -> dict[str, Any] | None:
    """Return metadata only; missing files are reported with ``exists=False``."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return {
            "exists": False,
            "owner": None,
            "group": None,
            "mode": None,
            "mtime": None,
            "size": None,
            "is_symlink": False,
            "link_target_scope": "none",
        }
    except (OSError, PermissionError):
        return None
    is_symlink = stat.S_ISLNK(info.st_mode)
    scope = "none"
    if is_symlink:
        try:
            target = Path(os.readlink(path))
            resolved = (Path(path).parent / target).resolve()
            scope = "local" if resolved.is_relative_to(Path(path).parent.resolve()) else "external"
        except OSError:
            scope = "unknown"
    return {
        "exists": True,
        "owner": _owner(info.st_uid),
        "group": _group(info.st_gid),
        "mode": format(stat.S_IMODE(info.st_mode), "04o"),
        "mtime": _mtime(info.st_mtime),
        "size": info.st_size,
        "is_symlink": is_symlink,
        "link_target_scope": scope,
    }


def hash_file(path: str | Path, max_bytes: int = MAX_HASH_BYTES) -> str | None:
    """Return a chunked SHA-256, or None for missing/oversized/unreadable files."""
    try:
        if os.path.getsize(path) > max_bytes:
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while chunk := handle.read(65536):
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, PermissionError):
        return None


def list_directory(
    path: str | Path, *, recursive: bool = False, max_entries: int = 2000
) -> list[dict[str, Any]]:
    """List entry metadata, hashing only small regular files."""
    entries: list[dict[str, Any]] = []
    root = Path(path)
    try:
        if recursive:
            walker = os.walk(root, followlinks=False)
            directories = list(walker)
        else:
            directories = [(str(root), [], [entry.name for entry in root.iterdir()])]
    except (OSError, PermissionError):
        return entries
    for folder, _subdirs, files in directories:
        for name in files:
            if len(entries) >= max_entries:
                return entries
            candidate = Path(folder) / name
            try:
                info = os.lstat(candidate)
            except OSError:
                continue
            entry: dict[str, Any] = {
                "name": str(candidate.relative_to(root)),
                "mode": format(stat.S_IMODE(info.st_mode), "04o"),
                "owner": _owner(info.st_uid),
                "group": _group(info.st_gid),
                "size": info.st_size,
                "mtime": _mtime(info.st_mtime),
                "sha256": hash_file(candidate) if stat.S_ISREG(info.st_mode) else None,
            }
            entries.append(entry)
    return entries


def ssh_key_fingerprints(path: str | Path) -> list[str]:
    """Return SHA256 fingerprints for authorized_keys entries, never key text."""
    fingerprints: list[str] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except (OSError, PermissionError):
        return fingerprints
    for line in lines:
        parts = line.split()
        if len(parts) < 2 or not parts[0].startswith(("ssh-", "ecdsa-", "sk-")):
            continue
        try:
            blob = base64.b64decode(parts[1], validate=True)
        except (binascii.Error, ValueError):
            continue
        digest = hashlib.sha256(blob).digest()
        encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
        fingerprints.append("SHA256:" + encoded)
    return fingerprints
