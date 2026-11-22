"""Fake feed adapters for the simulator.

The real collectors run unchanged; only their machine-state inputs are
replaced with deterministic, injected records. No psutil call reaches the host,
no socket is opened and no subprocess is started.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import psutil

from scripts.simulator.generators import FeedRecord

_BASE_LISTENER = FeedRecord(
    at=datetime.min.replace(tzinfo=UTC),
    kind="listener",
    payload={"port": 22, "address": "127.0.0.1", "pid": 1, "name": "sshd"},
)
_BASE_PROCESS = FeedRecord(
    at=datetime.min.replace(tzinfo=UTC),
    kind="process",
    payload={
        "pid": 1,
        "name": "init",
        "exe": "/usr/sbin/init",
        "username": "root",
        "create_time": 0,
    },
)


def _address(ip: str, port: int) -> Any:
    return SimpleNamespace(ip=ip, port=port)


class FakeFeeds:
    """Deterministic stand-in for network, listener and process machine state."""

    def __init__(self, records: list[FeedRecord] | None = None) -> None:
        self.records = list(records or [])

    def _due(self, kind: str, now: datetime) -> list[FeedRecord]:
        return [
            item
            for item in ([_BASE_LISTENER, _BASE_PROCESS] if kind != "connection" else [])
            + self.records
            if item.kind == kind and item.at <= now
        ]

    @contextmanager
    def installed(self, now: datetime) -> Iterator[None]:
        """Patch collector inputs for one simulated cycle, then restore them."""
        from unittest.mock import patch

        def connections(**_kwargs: Any) -> list[Any]:
            result: list[Any] = []
            for record in self._due("listener", now):
                payload = record.payload
                result.append(
                    SimpleNamespace(
                        laddr=_address(
                            str(payload.get("address", "127.0.0.1")), int(payload.get("port", 0))
                        ),
                        raddr=_address("", 0),
                        status=psutil.CONN_LISTEN,
                        type="STREAM",
                        pid=int(payload.get("pid", 0)),
                    )
                )
            for record in self._due("connection", now):
                payload = record.payload
                result.append(
                    SimpleNamespace(
                        laddr=_address("127.0.0.1", 40000),
                        raddr=_address(
                            str(payload.get("address", "198.51.100.9")),
                            int(payload.get("port", 443)),
                        ),
                        status="ESTABLISHED",
                        type="STREAM",
                        pid=int(payload.get("pid", 2)),
                    )
                )
            return result

        def process_iter(_attrs: Any = None) -> list[Any]:
            return [
                SimpleNamespace(info=dict(record.payload)) for record in self._due("process", now)
            ]

        def details(pid: int | None) -> tuple[str | None, str | None]:
            for record in self.records + [_BASE_LISTENER, _BASE_PROCESS]:
                if (
                    record.kind in {"process", "listener"}
                    and int(record.payload.get("pid", -1)) == pid
                ):
                    return str(record.payload.get("name", "unknown")), str(
                        record.payload.get("username", "unknown")
                    )
            return None, None

        with (
            patch("collectors.network.psutil.net_connections", connections),
            patch("collectors.listening.psutil.net_connections", connections),
            patch("collectors.processes.psutil.process_iter", process_iter),
            patch("collectors.network.get_process_details", details),
            patch("collectors.listening.get_process_details", details),
        ):
            yield
