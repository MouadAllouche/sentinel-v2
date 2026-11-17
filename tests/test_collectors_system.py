"""Tests for journald, dpkg, psutil snapshot collectors and filesystem helpers (Phase 3)."""

# ruff: noqa: S104, S108 - fixtures model 0.0.0.0 binds and /tmp executables; no real bind/open.
from __future__ import annotations

import base64
import hashlib
import json
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

import psutil
import pytest

from collectors import dpkg, filesystem, journald, listening, network, processes, system
from collectors.logs import parse_auth_line
from core import timeutil
from core.events import validate_event
from core.normalizer import compute_event_hash, normalize_event


@pytest.fixture(autouse=True)
def fixed_local_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timeutil, "_local_tzinfo", lambda: UTC)


def _journal_entry(message: str, timestamp: datetime, cursor: str = "cursor-1") -> str:
    return json.dumps(
        {
            "MESSAGE": message,
            "__CURSOR": cursor,
            "__REALTIME_TIMESTAMP": str(int(timestamp.timestamp() * 1_000_000)),
        }
    )


def test_journald_uses_argument_list_and_parses_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    captured: dict[str, Any] = {}

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=_journal_entry("Failed password for admin from 203.0.113.45", now) + "\n",
            stderr="",
        )

    monkeypatch.setattr(journald.subprocess, "run", fake_run)
    result = journald.collect_journald_events("ssh", {}, now=now)
    assert len(result.events) == 1
    assert result.events[0]["event_type"] == "failed_login"
    assert result.state is not None and result.state["cursor"] == "cursor-1"
    assert captured["args"][0] == "journalctl"
    assert "--no-pager" in captured["args"]
    assert "-u" in captured["args"] and "ssh" in captured["args"]
    assert "shell" not in captured["kwargs"]
    assert captured["kwargs"]["check"] is False


def test_journald_prefers_timestamp_embedded_in_message(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp = datetime(2026, 11, 15, 1, 24, 19, 424500, tzinfo=UTC)
    later = datetime(2026, 11, 15, 2, 0, tzinfo=UTC)
    line = f"{timestamp.isoformat()} srv sshd[812]: Failed password for admin from 203.0.113.45"
    entry = json.dumps(
        {
            "MESSAGE": line,
            "__CURSOR": "cursor-9",
            "__REALTIME_TIMESTAMP": str(int(later.timestamp() * 1_000_000)),
        }
    )
    monkeypatch.setattr(
        journald.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=entry + "\n", stderr=""),
    )
    result = journald.collect_journald_events("ssh", {}, now=later)
    assert len(result.events) == 1
    assert result.events[0]["timestamp"] == timestamp.isoformat()


def test_journald_missing_binary_is_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("journalctl")

    monkeypatch.setattr(journald.subprocess, "run", missing)
    result = journald.collect_journald_events("ssh", {})
    assert result.events == []
    assert result.warnings


def test_both_mode_timestamps_deduplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamp = datetime(2026, 11, 15, 1, 24, 19, 424500, tzinfo=UTC)
    iso = timestamp.isoformat()
    line = f"{iso} srv sshd[812]: Failed password for admin from 203.0.113.45 port 52114 ssh2"
    from_log = parse_auth_line(line, year=2026)
    assert from_log is not None

    monkeypatch.setattr(
        journald.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout=_journal_entry("Failed password for admin from 203.0.113.45", timestamp) + "\n",
            stderr="",
        ),
    )
    from_journald = journald.collect_journald_events("ssh", {}, now=timestamp).events
    assert len(from_journald) == 1
    assert compute_event_hash(normalize_event(from_log)) == compute_event_hash(
        normalize_event(from_journald[0])
    )


@pytest.mark.parametrize(
    ("line", "expected_type", "package"),
    [
        ("2026-11-15 10:00:00 install nmap:amd64 <none> 7.95-1", "package_installed", "nmap:amd64"),
        ("2026-11-15 10:00:01 remove nmap:amd64 7.95-1", "package_removed", "nmap:amd64"),
        ("2026-11-15 10:00:02 purge hydra 9.5-1", "package_removed", "hydra"),
    ],
)
def test_dpkg_parser(line: str, expected_type: str, package: str) -> None:
    event = dpkg.parse_dpkg_line(line)
    assert event is not None
    assert event["event_type"] == expected_type
    assert event["details"]["package"] == package
    assert validate_event(event) is True


def test_dpkg_parser_ignores_unrelated_lines() -> None:
    assert dpkg.parse_dpkg_line("2026-11-15 10:00:00 startup packages configure") is None


def test_dpkg_incremental_collection(tmp_path: Path) -> None:
    path = tmp_path / "dpkg.log"
    path.write_text("2026-11-15 10:00:00 install nmap:amd64 <none> 7.95-1\npartial")
    first = dpkg.collect_dpkg_events(path, {})
    assert len(first.events) == 1
    second = dpkg.collect_dpkg_events(path, first.state)
    assert second.events == []


def test_network_state_diff_and_process_details(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = NS(
        status="ESTABLISHED",
        laddr=NS(ip="10.0.0.5", port=40000),
        raddr=NS(ip="203.0.113.9", port=443),
        pid=42,
    )
    listen = NS(status="LISTEN", laddr=NS(ip="0.0.0.0", port=22), raddr=None, pid=1)
    without_raddr = NS(
        status="ESTABLISHED", laddr=NS(ip="10.0.0.5", port=40001), raddr=None, pid=42
    )
    monkeypatch.setattr(
        network.psutil,
        "net_connections",
        lambda kind: [connection, listen, without_raddr],
    )
    monkeypatch.setattr(
        network.psutil,
        "Process",
        lambda pid: NS(name=lambda: "sshd", username=lambda: "alice"),
    )
    now = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    first = network.collect_network_events({}, now=now)
    assert len(first.events) == 1
    event = first.events[0]
    assert event.get("source_ip") is None
    assert event["local_ip"] == "10.0.0.5"
    assert event["destination_ip"] == "203.0.113.9"
    assert event["destination_port"] == 443
    assert event["process_name"] == "sshd"
    assert event["username"] == "alice"
    assert validate_event(event) is True
    second = network.collect_network_events(first.state, now=now)
    assert second.events == []


def test_network_empty_snapshot_and_missing_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(network.psutil, "net_connections", lambda kind: [])
    assert network.collect_network_events({}).events == []
    connection = NS(
        status="ESTABLISHED",
        laddr=NS(ip="10.0.0.5", port=40000),
        raddr=NS(ip="203.0.113.9", port=443),
        pid=None,
    )
    monkeypatch.setattr(network.psutil, "net_connections", lambda kind: [connection])
    result = network.collect_network_events({})
    assert len(result.events) == 1
    assert result.events[0]["process_id"] is None
    assert validate_event(normalize_event(result.events[0])) is True


def test_network_process_details_degrade(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(pid: int) -> object:
        raise psutil.AccessDenied(pid=pid)

    monkeypatch.setattr(network.psutil, "Process", denied)
    assert network.get_process_details(None) == (None, None)
    assert network.get_process_details(42) == (None, None)


def test_network_access_denied_becomes_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(kind: str) -> object:
        raise psutil.AccessDenied()

    monkeypatch.setattr(network.psutil, "net_connections", denied)
    result = network.collect_network_events({})
    assert result.events == []
    assert result.warnings


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("127.0.0.1", "loopback"),
        ("10.0.0.5", "private"),
        ("0.0.0.0", "all_interfaces"),
        ("8.8.8.8", "public"),
    ],
)
def test_listening_bind_scope(address: str, expected: str) -> None:
    assert listening.classify_bind_scope(address) == expected


def test_listening_first_run_then_new_port(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = NS(
        status="LISTEN",
        laddr=NS(ip="0.0.0.0", port=22),
        raddr=None,
        pid=1,
        type=socket.SOCK_STREAM,
    )
    monkeypatch.setattr(listening.psutil, "net_connections", lambda kind: [conn])
    monkeypatch.setattr(
        listening.psutil, "Process", lambda pid: NS(name=lambda: "sshd", username=lambda: "root")
    )
    first = listening.collect_listening_events({})
    assert first.events == []
    assert first.state is not None and first.state["seeded"] is True
    second_conn = NS(
        status="LISTEN",
        laddr=NS(ip="0.0.0.0", port=8080),
        raddr=None,
        pid=2,
        type=socket.SOCK_STREAM,
    )
    monkeypatch.setattr(listening.psutil, "net_connections", lambda kind: [conn, second_conn])
    later = listening.collect_listening_events(first.state)
    assert len(later.events) == 1
    assert later.events[0]["details"]["bind_scope"] == "all_interfaces"
    assert later.events[0]["details"]["port"] == 8080


def _proc(pid: int, name: str, exe: str, create_time: float = 100.0) -> NS:
    return NS(
        info={
            "pid": pid,
            "ppid": 1,
            "name": name,
            "username": "alice",
            "exe": exe,
            "create_time": create_time,
        }
    )


def test_processes_first_run_suspicious_only(monkeypatch: pytest.MonkeyPatch) -> None:
    procs = [_proc(1, "systemd", "/usr/lib/systemd/systemd"), _proc(2, "payload", "/tmp/payload")]
    monkeypatch.setattr(processes.psutil, "process_iter", lambda attrs: procs)
    result = processes.collect_process_events({})
    assert len(result.events) == 1
    assert result.events[0]["event_type"] == "suspicious_process"
    assert "cmdline" not in str(result.events[0])
    assert result.state is not None and result.state["seeded"] is True


def test_processes_new_process_and_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = [_proc(1, "systemd", "/usr/lib/systemd/systemd")]
    monkeypatch.setattr(processes.psutil, "process_iter", lambda attrs: baseline)
    first = processes.collect_process_events({})
    extended = baseline + [_proc(i, f"tool-{i}", f"/usr/bin/tool-{i}") for i in range(2, 7)]
    monkeypatch.setattr(processes.psutil, "process_iter", lambda attrs: extended)
    result = processes.collect_process_events(first.state, max_events=2)
    assert len(result.events) == 2
    assert all(event["event_type"] == "process_started" for event in result.events)
    assert result.warnings


def test_processes_deleted_exe_is_suspicious(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        processes.psutil, "process_iter", lambda attrs: [_proc(9, "gone", "(deleted)")]
    )
    result = processes.collect_process_events({})
    assert result.events[0]["event_type"] == "suspicious_process"


def test_filesystem_helpers(tmp_path: Path) -> None:
    target = tmp_path / "sample"
    target.write_text("secret contents must never be returned")
    target.chmod(0o644)
    metadata = filesystem.get_file_metadata(target)
    assert metadata is not None
    assert metadata["exists"] is True
    assert metadata["mode"] == "0644"
    assert metadata["size"] == len("secret contents must never be returned")
    assert filesystem.hash_file(target) == hashlib.sha256(target.read_bytes()).hexdigest()
    assert "secret" not in str(metadata)

    subdir = tmp_path / "keys"
    subdir.mkdir()
    (subdir / "one").write_text("data")
    entries = filesystem.list_directory(subdir, recursive=False, max_entries=10)
    assert [entry["name"] for entry in entries] == ["one"]
    assert filesystem.get_file_metadata(tmp_path / "missing") is not None

    blob = base64.b64encode(b"a-fake-public-key-blob").decode("ascii")
    authorized = tmp_path / "authorized_keys"
    authorized.write_text(f"ssh-ed25519 {blob} alice@host\ninvalid line\nssh-rsa {blob}\n")
    fingerprints = filesystem.ssh_key_fingerprints(authorized)
    expected = "SHA256:" + base64.b64encode(
        hashlib.sha256(b"a-fake-public-key-blob").digest()
    ).decode("ascii").rstrip("=")
    assert fingerprints == [expected, expected]
    assert "alice" not in str(fingerprints)


def test_filesystem_symlink_and_unreadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "real"
    target.write_text("data")
    link = tmp_path / "link"
    link.symlink_to(target)
    metadata = filesystem.get_file_metadata(link)
    assert metadata is not None
    assert metadata["is_symlink"] is True
    assert metadata["link_target_scope"] == "local"

    unreadable = tmp_path / "unreadable"
    unreadable.write_text("data")
    real_open = open

    def deny(file: object, *args: object, **kwargs: object) -> object:
        if str(file) == str(unreadable):
            raise PermissionError("denied")
        return real_open(file, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("builtins.open", deny)
    assert filesystem.hash_file(unreadable) is None


def test_system_info_event() -> None:
    event = system.collect_system_info(now=datetime(2026, 11, 15, 10, tzinfo=UTC))
    assert event["event_type"] == "system_info"
    assert event["source"] == "system"
    for key in (
        "hostname",
        "kernel",
        "boot_time",
        "uptime_seconds",
        "cpu_percent",
        "memory_percent",
        "logged_in_users",
    ):
        assert key in event["details"]
    assert validate_event(event) is True
