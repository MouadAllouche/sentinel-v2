"""Phase 20 CLI and what-if tests — written before the implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cli import main
from scripts.simulator.runner import whatif
from scripts.simulator.scenarios import DEFAULT_RULE_IDS

SEED = 7


def test_cli_list_run_whatif_and_dashboard(
    tmp_path: Path, sim_workdir: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert main(["simulate", "list"]) == 0
    listed = capsys.readouterr().out
    assert "ssh-bruteforce-single-ip" in listed
    assert "benign-admin-day" in listed

    out = sim_workdir / "reports"
    assert (
        main(
            [
                "simulate",
                "run",
                "ssh-bruteforce-single-ip",
                "--seed",
                str(SEED),
                "--format",
                "json",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert isinstance(report, dict) and report["scenarios"]

    assert main(["simulate", "run", "does-not-exist"]) == 2

    dashboard_out = sim_workdir / "dash"
    assert main(["simulate", "dashboard", "--seed", str(SEED), "--out", str(dashboard_out)]) == 0
    assert (dashboard_out / "sim.db").exists()
    assert (dashboard_out / "session.key").exists()


def test_whatif_reports_diff_and_does_not_mutate_defaults(
    tmp_path: Path, sim_workdir: Path
) -> None:
    from storage.rules_repository import list_rules

    rules_file = tmp_path / "rules.json"
    rules_file.write_text(
        json.dumps(
            [
                {
                    "id": "ssh-bruteforce-by-ip",
                    "name": "Lowered brute force",
                    "description": "What-if rule",
                    "kind": "threshold",
                    "enabled": True,
                    "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
                    "scope": {"exclude_allowlisted": True},
                    "actions": {"create_incident": True, "notify": True, "tags": []},
                    "mitre": [],
                    "group_by": ["source_ip"],
                    "aggregate": {"type": "count"},
                    "window_mode": "sliding",
                    "cooldown_seconds": 0,
                    "tiers": [
                        {
                            "label": "Low",
                            "count": 3,
                            "window_seconds": 600,
                            "severity": "medium",
                            "points": 10,
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    diff = whatif("low-and-slow", rules_file, seed=SEED, workdir=sim_workdir)
    assert "findings_gained" in diff
    assert "findings_lost" in diff
    assert "score_change" in diff
    assert "time_to_detect_change" in diff
    # The seeded rule set used for normal scenarios is untouched.
    default_db = sim_workdir / "whatif-default" / "low-and-slow" / "low-and-slow.db"
    ids_from_defaults = {rule.id for rule in list_rules(db_path=default_db)}
    assert ids_from_defaults >= DEFAULT_RULE_IDS


def test_whatif_rejects_invalid_rule_file(tmp_path: Path, sim_workdir: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        whatif("ssh-bruteforce-single-ip", bad, seed=SEED, workdir=sim_workdir)


def test_cli_whatif_and_live_flags(tmp_path: Path, sim_workdir: Path, capsys: Any) -> None:
    rules = tmp_path / "rules.json"
    rules.write_text("[]", encoding="utf-8")
    assert (
        main(
            [
                "simulate",
                "whatif",
                "ssh-bruteforce-single-ip",
                "--rules",
                str(rules),
                "--seed",
                str(SEED),
                "--out",
                str(sim_workdir / "wi"),
            ]
        )
        == 0
    )
    assert "findings gained" in capsys.readouterr().out.lower()
    # live with speed and a bounded step count must stop cleanly (dry mode).
    assert (
        main(
            [
                "simulate",
                "live",
                "--speed",
                "1000",
                "--steps",
                "2",
                "--out",
                str(sim_workdir / "live"),
            ]
        )
        == 0
    )
