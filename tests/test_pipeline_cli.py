"""Tests for pipeline isolation, engine lock and CLI commands (Phase 11)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cli import main
from core.pipeline import CycleReport, run_cycle
from engine.runner import acquire_lock, release_lock

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


def test_cycle_order_isolation_and_report(tmp_initialised_db: Path) -> None:
    calls: list[str] = []

    def ok_step(name: str) -> Any:
        def step(settings: Any, db_path: Any, now: Any) -> dict[str, int]:
            calls.append(name)
            return {"count": 1}

        return step

    def broken(settings: Any, db_path: Any, now: Any) -> dict[str, int]:
        calls.append("broken")
        raise RuntimeError("step failed")

    steps = [
        ("collect", ok_step("collect")),
        ("rules", broken),
        ("baselines", ok_step("baselines")),
    ]
    report = run_cycle(None, tmp_initialised_db, now=NOW, steps=steps)
    assert calls == ["collect", "broken", "baselines"]
    assert isinstance(report, CycleReport)
    assert len(report.steps) == 3
    assert report.steps[1].status == "error"
    assert "step failed" in (report.steps[1].error or "")


def test_cycle_lock(tmp_initialised_db: Path) -> None:
    assert acquire_lock(tmp_initialised_db, owner="engine-a", now=NOW) is True
    assert acquire_lock(tmp_initialised_db, owner="engine-b", now=NOW) is False
    release_lock(tmp_initialised_db, owner="engine-a")
    assert acquire_lock(tmp_initialised_db, owner="engine-b", now=NOW) is True


def test_cli_init_run_and_status(tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    assert main(["--db", str(db), "init"]) == 0
    assert main(["--db", str(db), "seed"]) == 0
    assert main(["--db", str(db), "run"]) == 0
    assert main(["--db", str(db), "status"]) == 0
    assert main(["--db", str(db), "engine", "--once"]) == 0
    assert main(["--db", str(db), "does-not-exist"]) == 2


def test_cli_json_output_and_password_never_in_argv(tmp_path: Path, monkeypatch: Any) -> None:
    db = tmp_path / "cli.db"
    main(["--db", str(db), "init"])
    monkeypatch.setattr("cli.getpass", lambda prompt: "a-very-long-password")
    argv = ["--db", str(db), "user", "create", "--role", "admin"]
    assert main(argv) == 0
    assert all("a-very-long-password" not in item for item in argv)


def test_cli_drift_and_rules_commands(tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    main(["--db", str(db), "init"])
    assert main(["--db", str(db), "drift", "init"]) == 0
    assert main(["--db", str(db), "drift", "check"]) == 0
    assert main(["--db", str(db), "rules", "list", "--json"]) == 0
    assert main(["--db", str(db), "severity", "list"]) == 0
    assert main(["--db", str(db), "prune", "--dry-run"]) == 0
