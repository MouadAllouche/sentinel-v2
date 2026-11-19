"""Tests for pure drift comparison and safe snapshot collection (Phase 9)."""

# ruff: noqa: S108 - '/tmp/file' is a path-validation fixture, never opened.
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from collectors import filesystem
from core.drift_detection import (
    PathSpec,
    compare_snapshots,
    describe_changes,
    flags_for,
    validate_path,
)

SPEC = PathSpec(
    id=1,
    path="/etc/ssh/sshd_config",
    kind="file",
    sensitivity="high",
    category="ssh",
    metadata_only=False,
)


def _snapshot(**changes: Any) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "path": SPEC.path,
        "exists": True,
        "kind": "file",
        "sha256": "a" * 64,
        "owner": "root",
        "group": "root",
        "mode": "0644",
        "mtime": "2026-11-15T10:00:00+00:00",
        "size": 100,
        "is_symlink": False,
        "extra": {},
        "warnings": [],
    }
    snapshot.update(changes)
    return snapshot


def test_no_change_produces_no_changes() -> None:
    snapshot = _snapshot()
    assert compare_snapshots(snapshot, dict(snapshot), SPEC) == []


def test_content_and_mode_changes_with_flags() -> None:
    current = _snapshot(sha256="b" * 64, mode="0777")
    changes = compare_snapshots(_snapshot(), current, SPEC)
    fields = {change.field for change in changes}
    assert {"sha256", "mode"} <= fields
    flags = flags_for(_snapshot(), current, changes)
    assert "world_writable" in flags
    descriptions = describe_changes(changes, SPEC, flags, only_mtime=False)
    assert any("permissions changed from 0644 to 0777" in text for text in descriptions)


def test_only_mtime_flag() -> None:
    current = _snapshot(mtime="2026-11-15T11:00:00+00:00")
    changes = compare_snapshots(_snapshot(), current, SPEC)
    assert {change.field for change in changes} == {"mtime"}
    assert flags_for(_snapshot(), current, changes) == []
    assert describe_changes(changes, SPEC, [], only_mtime=True)[0].endswith("(mtime only)")


def test_owner_group_and_symlink_flags() -> None:
    previous = _snapshot(owner="root")
    current = _snapshot(owner="alice", group="wheel", mode="4755")
    changes = compare_snapshots(previous, current, SPEC)
    flags = flags_for(previous, current, changes)
    assert "owner_changed_to_nonroot" in flags
    assert "setuid_added" in flags
    assert "group_writable_added" not in flags


def test_added_removed_and_directory_entries() -> None:
    added = compare_snapshots(_snapshot(exists=False), _snapshot(), SPEC)
    assert any(change.field == "exists" for change in added)
    removed = compare_snapshots(_snapshot(), _snapshot(exists=False), SPEC)
    assert any(change.field == "exists" for change in removed)

    dir_spec = PathSpec(
        id=2,
        path="/etc/cron.d",
        kind="dir",
        sensitivity="high",
        category="cron",
        metadata_only=False,
    )
    previous = _snapshot(
        kind="dir",
        extra={
            "entries": [
                {"name": "old", "mode": "0644", "sha256": "a" * 64},
            ]
        },
    )
    current = _snapshot(
        kind="dir",
        extra={
            "entries": [
                {"name": "new", "mode": "0755", "sha256": "b" * 64},
                {"name": "old", "mode": "0644", "sha256": "c" * 64},
            ]
        },
    )
    changes = compare_snapshots(previous, current, dir_spec)
    fields = {change.field for change in changes}
    assert {"entries_added", "entries_modified"} <= fields
    text = describe_changes(changes, dir_spec, [], only_mtime=False)
    assert any("new file 'new'" in item for item in text)


def test_authorized_keys_fingerprints_only() -> None:
    key_spec = PathSpec(
        id=3,
        path="/root/.ssh/authorized_keys",
        kind="authorized_keys",
        sensitivity="critical",
        category="authorized_keys",
        metadata_only=False,
    )
    previous = _snapshot(kind="authorized_keys", extra={"fingerprints": ["SHA256:old"]})
    current = _snapshot(
        kind="authorized_keys", extra={"fingerprints": ["SHA256:old", "SHA256:new"]}
    )
    changes = compare_snapshots(previous, current, key_spec)
    assert any(change.field == "fingerprints_added" for change in changes)
    text = describe_changes(changes, key_spec, [], only_mtime=False)
    assert any("1 key added" in item for item in text)
    assert "SHA256:new" in " ".join(text)


def test_real_key_fingerprints_and_malformed_lines(tmp_path: Path) -> None:
    import base64
    import hashlib

    blob = base64.b64encode(b"a-sample-public-key-blob").decode("ascii")
    keys = tmp_path / "authorized_keys"
    keys.write_text(
        f"ssh-ed25519 {blob} alice@host\n"
        "invalid line without a key\n"
        f"ecdsa-sha2-nistp256 {blob} bob@host\n"
    )
    fingerprints = filesystem.ssh_key_fingerprints(keys)
    expected = "SHA256:" + base64.b64encode(
        hashlib.sha256(b"a-sample-public-key-blob").digest()
    ).decode("ascii").rstrip("=")
    assert fingerprints == [expected, expected]
    assert "alice" not in str(fingerprints)


def test_symlink_target_change(tmp_path: Path) -> None:
    target_a, target_b = tmp_path / "a", tmp_path / "b"
    target_a.write_text("a")
    target_b.write_text("b")
    link = tmp_path / "link"
    link.symlink_to(target_a)
    spec = PathSpec(id=9, path=str(link), kind="file", sensitivity="low", category="other")
    first, _ = filesystem.take_snapshot(spec)
    assert first["is_symlink"] is True
    second = dict(first)
    second["extra"] = {**first["extra"], "link_target_scope": "external"}
    changes = compare_snapshots(first, second, spec)
    assert any(change.field == "symlink_target_changed" for change in changes)


def test_metadata_only_never_opens_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "shadow"
    target.write_text("secret")
    spec = PathSpec(
        id=4,
        path=str(target),
        kind="file",
        sensitivity="critical",
        category="system_account",
        metadata_only=True,
    )

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("metadata_only file was opened")

    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(filesystem, "hash_file", forbidden)
    snapshot, warnings = filesystem.take_snapshot(spec, now=datetime(2026, 11, 15, tzinfo=UTC))
    assert snapshot["sha256"] is None
    assert snapshot["exists"] is True
    assert warnings == []


def test_unreadable_file_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "unreadable"
    target.write_text("data")
    spec = PathSpec(
        id=5,
        path=str(target),
        kind="file",
        sensitivity="high",
        category="ssh",
        metadata_only=False,
    )
    real_open = open

    def deny(file: object, *args: object, **kwargs: object) -> object:
        if str(file) == str(target):
            raise PermissionError("denied")
        return real_open(file, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("builtins.open", deny)
    snapshot, warnings = filesystem.take_snapshot(spec, now=datetime(2026, 11, 15, tzinfo=UTC))
    assert snapshot["sha256"] is None
    assert any("hash unavailable" in warning for warning in warnings)


@pytest.mark.parametrize(
    ("path", "valid"),
    [
        ("/etc/passwd", True),
        ("/etc/../etc/passwd", False),
        ("etc/passwd", False),
        ("/home/alice/file", True),
        ("/tmp/file", False),
    ],
)
def test_path_validation(path: str, valid: bool) -> None:
    if valid:
        assert validate_path(path) == path
    else:
        with pytest.raises(ValueError):
            validate_path(path)


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    mode=st.sampled_from(["0644", "0600", "0777", "4755"]), owner=st.sampled_from(["root", "alice"])
)
def test_compare_never_raises(mode: str, owner: str) -> None:
    previous = _snapshot()
    current = _snapshot(mode=mode, owner=owner)
    changes = compare_snapshots(previous, current, SPEC)
    assert isinstance(changes, list)
    assert isinstance(describe_changes(changes, SPEC, [], False), list)
