"""Read-only collectors of Linux system state.

Collectors return raw-ish event dicts plus warnings and the state to persist
*after* those events have been saved. They never modify the monitored system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CollectionResult:
    events: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    state: dict[str, Any] | None = None
