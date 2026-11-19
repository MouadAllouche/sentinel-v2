"""Pure cycle orchestration: isolated, timed, reported steps.

The actual I/O steps are injected by ``engine/runner.py`` so this module stays
free of database, clock and filesystem access.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any

__all__ = ["CycleReport", "StepReport", "run_cycle"]


@dataclass
class StepReport:
    name: str
    status: str
    duration_ms: int
    counts: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class CycleReport:
    steps: list[StepReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(step.status == "ok" for step in self.steps)

    @property
    def warnings(self) -> list[str]:
        return [f"{step.name}: {warning}" for step in self.steps for warning in step.warnings]


def run_cycle(
    settings: Any,
    db_path: Any,
    now: datetime | None = None,
    *,
    steps: list[tuple[str, Callable[..., Any]]] | None = None,
) -> CycleReport:
    """Run each step independently; a failing step never stops later steps."""
    report = CycleReport()
    for name, step in steps or []:
        started = perf_counter()
        warnings: list[str] = []
        try:
            result = step(settings, db_path, now)
            if isinstance(result, dict):
                counts = dict(result)
                warnings = [str(item) for item in counts.pop("warnings", [])]
            elif result is None:
                counts = {}
            else:
                counts = {"result": result}
            status, error = "ok", None
        except Exception as exc:  # noqa: BLE001 - isolation is the point
            counts, status, error = {}, "error", f"{type(exc).__name__}: {exc}"
        report.steps.append(
            StepReport(
                name=name,
                status=status,
                duration_ms=int((perf_counter() - started) * 1000),
                counts=counts,
                warnings=warnings,
                error=error,
            )
        )
    return report
