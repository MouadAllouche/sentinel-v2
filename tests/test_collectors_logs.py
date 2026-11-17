"""Tests for auth.log parsing and incremental collection (Phase 3)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from collectors.logs import (
    collect_auth_events,
    extract_timestamp,
    parse_auth_line,
    state_key,
)
from core import timeutil
from core.events import validate_event


@pytest.fixture(autouse=True)
def fixed_local_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timeutil, "_local_tzinfo", lambda: UTC)


@pytest.mark.parametrize(
    ("line", "expected_type", "expected_fields"),
    [
        (
            "2026-11-15T01:24:19.424500+00:00 srv sshd[812]: "
            "Failed password for invalid user admin from 203.0.113.45 port 52114 ssh2",
            "failed_login",
            {"username": "admin", "source_ip": "203.0.113.45"},
        ),
        (
            "Nov  4 10:30:15 srv sshd[7]: "
            "Accepted publickey for alice from 198.51.100.7 port 50001 ssh2",
            "successful_login",
            {"username": "alice", "source_ip": "198.51.100.7"},
        ),
        (
            "Nov  4 10:30:15 srv sshd[7]: Invalid user bob from 203.0.113.9",
            "invalid_user",
            {"username": "bob", "source_ip": "203.0.113.9"},
        ),
        (
            "Nov  4 10:30:15 srv sshd[7]: "
            "Connection closed by authenticating user carol 203.0.113.45 port 52114 [preauth]",
            "preauth_disconnect",
            {"username": "carol", "source_ip": "203.0.113.45"},
        ),
        (
            "Nov  4 10:30:15 srv sudo:   alice : TTY=pts/0 ; PWD=/home/alice ; "
            "USER=root ; COMMAND=/usr/bin/visudo -c",
            "sudo_command",
            {"username": "alice", "process_name": "visudo"},
        ),
        (
            "Nov  4 10:30:15 srv su[123]: (to root) alice on pts/0",
            "su_command",
            {"username": "alice"},
        ),
        (
            "Nov  4 10:30:15 srv useradd[9]: new user: name=dave, UID=1001, GID=1001",
            "user_created",
            {},
        ),
        ("Nov  4 10:30:15 srv userdel[9]: delete user 'dave'", "user_deleted", {}),
        (
            "Nov  4 10:30:15 srv usermod[9]: add 'dave' to shadow group 'sudo'",
            "group_member_added",
            {},
        ),
        ("Nov  4 10:30:15 srv passwd[9]: password changed for dave", "password_changed", {}),
    ],
)
def test_auth_patterns(line: str, expected_type: str, expected_fields: dict[str, str]) -> None:
    event = parse_auth_line(line, year=2026)
    assert event is not None
    assert event["event_type"] == expected_type
    assert event["severity"] == "low"
    assert event["source"] == "auth_log"
    assert validate_event(event) is True
    for key, value in expected_fields.items():
        assert event[key] == value


def test_sudo_details_never_store_arguments() -> None:
    line = (
        "Nov  4 10:30:15 srv sudo:   alice : TTY=pts/0 ; USER=root ; "
        "COMMAND=/usr/bin/visudo -c --secret"
    )
    event = parse_auth_line(line, year=2026)
    assert event is not None
    assert event["details"] == {
        "target_user": "root",
        "command_executable": "/usr/bin/visudo",
        "command_args_count": 2,
    }
    assert "secret" not in str(event)


def test_unrelated_line_returns_none() -> None:
    assert parse_auth_line("Nov  4 10:30:15 srv cron[1]: (root) CMD (true)", year=2026) is None


def test_invalid_user_and_failed_invalid_user_both_parse() -> None:
    failed = parse_auth_line(
        "Nov  4 10:30:15 srv sshd[1]: "
        "Failed password for invalid user invaliduseradmin from 203.0.113.9",
        year=2026,
    )
    invalid = parse_auth_line(
        "Nov  4 10:30:15 srv sshd[1]: Invalid user invaliduseradmin from 203.0.113.9",
        year=2026,
    )
    assert failed is not None and failed["event_type"] == "failed_login"
    assert invalid is not None and invalid["event_type"] == "invalid_user"


def test_extract_timestamp_iso_and_syslog() -> None:
    assert (
        extract_timestamp("2026-11-15T01:24:19.424500+00:00 srv sshd[1]: x", year=2026)
        == "2026-11-15T01:24:19.424500+00:00"
    )
    assert (
        extract_timestamp("Nov  4 10:30:15 srv sshd[1]: x", year=2026)
        == "2026-11-04T10:30:15+00:00"
    )


def test_extract_timestamp_year_rollover() -> None:
    now = datetime(2027, 1, 2, tzinfo=UTC)
    assert extract_timestamp("Dec 31 23:30:15 srv sshd[1]: x", now=now) == (
        "2026-12-31T23:30:15+00:00"
    )


def test_incremental_read_partial_lines_and_no_new_lines(tmp_path: Path) -> None:
    path = tmp_path / "auth.log"
    path.write_bytes(
        b"Nov  4 10:30:15 srv sshd[1]: Failed password for admin from 203.0.113.45\n"
        b"Nov  4 10:31:15 srv sshd[1]: Accepted password for admin from 203.0.113.45\n"
        b"Nov  4 10:32:15 srv sshd[1]: Failed password for bob from 203.0.113.46"
    )
    first = collect_auth_events(path, {}, now=datetime(2026, 11, 4, 12, tzinfo=UTC))
    assert len(first.events) == 2
    assert first.state is not None
    assert first.state["offset"] < path.stat().st_size
    second = collect_auth_events(path, first.state, now=datetime(2026, 11, 4, 12, tzinfo=UTC))
    assert second.events == []

    with path.open("ab") as handle:
        handle.write(
            b"\nNov  4 10:33:15 srv sshd[1]: Failed password for carol from 203.0.113.47\n"
        )
    third = collect_auth_events(path, second.state, now=datetime(2026, 11, 4, 12, tzinfo=UTC))
    assert len(third.events) == 2  # the previously partial line and the new one


def test_rotation_and_truncation_reset(tmp_path: Path) -> None:
    path = tmp_path / "auth.log"
    path.write_text("Nov  4 10:30:15 srv sshd[1]: Failed password for admin from 203.0.113.45\n")
    first = collect_auth_events(path, {}, year=2026)
    assert len(first.events) == 1
    path.write_text("Nov  4 10:40:15 srv sshd[1]: Invalid user bob from 203.0.113.46\n")
    after_truncate = collect_auth_events(path, first.state, year=2026)
    assert len(after_truncate.events) == 1
    path.unlink()
    path.write_text("Nov  4 10:50:15 Invalid user carol from 203.0.113.47\n")
    after_rotation = collect_auth_events(path, after_truncate.state, year=2026)
    assert len(after_rotation.events) == 1


def test_overlong_line_skipped_with_warning(tmp_path: Path) -> None:
    path = tmp_path / "auth.log"
    path.write_bytes(b"X" * 5000 + b"\n")
    result = collect_auth_events(path, {}, year=2026)
    assert result.events == []
    assert any("4096" in warning for warning in result.warnings)


def test_invalid_utf8_is_replaced(tmp_path: Path) -> None:
    path = tmp_path / "auth.log"
    path.write_bytes(b"Nov  4 10:30:15 srv sshd[1]: Invalid user \xffbob from 203.0.113.9\n")
    result = collect_auth_events(path, {}, year=2026)
    assert len(result.events) == 1
    assert validate_event(result.events[0]) is True


def test_permission_error_becomes_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "auth.log"
    path.write_text("nothing\n")
    real_open = open

    def deny(file: object, *args: object, **kwargs: object) -> object:
        if str(file) == str(path):
            raise PermissionError("denied")
        return real_open(file, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("builtins.open", deny)
    result = collect_auth_events(path, {}, year=2026)
    assert result.events == []
    assert result.warnings
    assert result.state is None


def test_state_key_uses_path() -> None:
    assert state_key(Path("/var/log/auth.log")) == "auth_log:/var/log/auth.log"
