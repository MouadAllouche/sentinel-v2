"""Simulator runs must start from a fresh sandbox (D-114 workdir defect)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SID = "ssh-bruteforce-single-ip"


def _run(out: Path) -> bytes:
    from cli import main

    assert main(["simulate", "run", SID, "--seed", "7", "--format", "json", "--out", str(out)]) == 0
    return (out / "report.json").read_bytes()


def _counts(report: bytes) -> dict[str, Any]:
    row = json.loads(report)["scenarios"][0]
    return {
        "findings": len(row["findings"]),
        "incidents": len(row["incidents"]),
        "outcome": row["outcome"],
        "score": row["score"],
    }


def test_same_scenario_twice_with_same_out_is_identical(sim_workdir: Path) -> None:
    out = sim_workdir / "twice"
    first = _run(out)
    first_counts = _counts(first)
    second = _run(out)
    assert second == first
    assert _counts(second) == first_counts
    assert first_counts["findings"] > 0 and first_counts["incidents"] > 0


def test_prepolluted_workdir_cannot_change_results(sim_workdir: Path) -> None:
    polluted = sim_workdir / "polluted"
    case = polluted / SID
    case.mkdir(parents=True)
    (case / f"{SID}.db").write_bytes(b"not a database")
    (case / "auth.log").write_text("garbage\n", encoding="utf-8")
    polluted_report = _run(polluted)
    clean_report = _run(sim_workdir / "clean")
    assert polluted_report == clean_report
    assert _counts(polluted_report) == _counts(clean_report)
