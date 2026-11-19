"""Notification data shapes. No I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Notification:
    kind: str
    incident_id: int
    severity: str
    title: str
    score: float
    reasons: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    target: str = ""
    status: str | None = None


@dataclass(frozen=True)
class Channel:
    id: int
    name: str
    kind: str
    enabled: bool
    config: dict[str, Any]
    min_severity: str = "high"
    filters: dict[str, Any] = field(default_factory=dict)
    throttle: dict[str, Any] = field(default_factory=dict)


class Transport(Protocol):
    def send(self, notification: Notification) -> bool: ...
