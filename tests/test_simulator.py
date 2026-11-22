"""Phase 20 threat simulator tests — written before the implementation."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.simulator.evaluate import aggregate, evaluate
from scripts.simulator.report import DISCLAIMER, render_json, render_markdown, render_table
from scripts.simulator.runner import build_dashboard, run_all, run_scenario
from scripts.simulator.scenarios import SCENARIOS, get_scenario, scenario_ids

SEED = 7
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def all_results() -> Any:
    """Run the full matrix once per test module (the runner is expensive)."""
    import shutil

    from scripts.simulator.runner import run_all

    target = ROOT / "sim_workdir" / "test-catalogue-results"
    if target.exists():
        shutil.rmtree(target)
    results = run_all(seed=SEED, workdir=target)
    yield {item.scenario_id: item for item in results}
    shutil.rmtree(target, ignore_errors=True)


EXPECTED_IDS = {
    "ssh-bruteforce-single-ip",
    "password-spraying",
    "distributed-bruteforce",
    "credential-compromise-chain",
    "scanner-preauth-flood",
    "login-from-new-ip",
    "backdoor-account",
    "persistence-cron",
    "persistence-ssh-key",
    "config-tampering",
    "suspicious-process",
    "unexpected-listener",
    "recon-tool-install",
    "failed-login-spike",
    "low-and-slow",
    "benign-admin-day",
    "benign-noisy-user",
    "benign-allowlisted-monitor",
    "mixed-realistic-week",
    "slow-rotating-bruteforce",
    "valid-user-spray-hourly",
    "stolen-credential-systemd-persistence",
    "shell-profile-preload-persistence",
    "ssh-key-plus-cron-delay",
    "dev-shm-staging",
    "legit-admin-3am",
    "blended-low-slow",
}


def test_catalogue_is_complete_and_typed() -> None:
    assert set(scenario_ids()) == EXPECTED_IDS
    assert len(SCENARIOS) == len(EXPECTED_IDS)
    for scenario in SCENARIOS:
        assert scenario.id in EXPECTED_IDS
        assert scenario.expectation.note
        assert scenario.mitre, f"{scenario.id} needs a MITRE tag"


_KNOWN_GAPS = {"slow-rotating-bruteforce", "valid-user-spray-hourly"}
_SCENARIO_PARAMS = [
    pytest.param(
        scenario_id,
        marks=pytest.mark.xfail(strict=True, reason="known detection gap, see D-113"),
    )
    if scenario_id in _KNOWN_GAPS
    else scenario_id
    for scenario_id in sorted(EXPECTED_IDS)
]


@pytest.mark.parametrize("scenario_id", _SCENARIO_PARAMS)
def test_scenario_expectation(scenario_id: str, all_results: dict[str, Any]) -> None:
    scenario = get_scenario(scenario_id)
    result = all_results[scenario_id]
    evaluation = evaluate(result)
    expected = scenario.expectation
    if scenario.category == "attack":
        assert evaluation.outcome == "TRUE_POSITIVE", (scenario_id, evaluation)
        assert evaluation.detected
        if expected.rules_any_of:
            assert set(expected.rules_any_of) & set(evaluation.matched_rules), (
                scenario_id,
                evaluation,
            )
    elif scenario.category == "evasion":
        assert evaluation.outcome in {"KNOWN_BLIND_SPOT", "UNEXPECTED_DETECTION"}
        if expected.should_detect is False and not evaluation.detected:
            assert evaluation.outcome == "KNOWN_BLIND_SPOT"
    elif scenario.category == "benign":
        assert evaluation.outcome in {"TRUE_NEGATIVE", "FALSE_POSITIVE"}
        assert evaluation.false_positives >= 0
        if expected.incident == "no":
            assert evaluation.incident_id is None
    else:  # combined
        assert evaluation.detected is True


def test_allowlisted_monitor_keeps_evidence_without_alert(all_results: dict[str, Any]) -> None:
    result = all_results["benign-allowlisted-monitor"]
    assert result.suppressed_count > 0
    assert result.events, "suppressed evidence must be stored, not dropped"
    assert result.incidents == []
    assert evaluate(result).outcome == "TRUE_NEGATIVE"


def test_determinism_same_seed_byte_identical_and_different_seed_same_outcomes(
    all_results: dict[str, Any],
) -> None:
    import shutil

    first = list(all_results.values())
    target = ROOT / "sim_workdir" / "test-determinism"
    if target.exists():
        shutil.rmtree(target)
    second = run_all(seed=SEED, workdir=target)
    assert render_json(first) == render_json(second)
    # A different seed must not change scenario outcomes.
    for scenario_id in ("ssh-bruteforce-single-ip", "benign-admin-day", "low-and-slow"):
        other = run_scenario(scenario_id, seed=SEED + 1, workdir=target / "other")
        assert evaluate(other).outcome == evaluate(all_results[scenario_id]).outcome
    shutil.rmtree(target, ignore_errors=True)


def test_sampled_cycles_match_full_60s_stepping(all_results: dict[str, Any]) -> None:
    """The coalesced stepping optimization must not change detection decisions."""
    import shutil

    target = ROOT / "sim_workdir" / "test-full-steps"
    if target.exists():
        shutil.rmtree(target)
    sampled = evaluate(all_results["ssh-bruteforce-single-ip"])
    full = evaluate(
        run_scenario("ssh-bruteforce-single-ip", seed=SEED, workdir=target, full_steps=True)
    )
    assert full.outcome == sampled.outcome == "TRUE_POSITIVE"
    assert set(full.matched_rules) == set(sampled.matched_rules)
    assert full.time_to_detect == sampled.time_to_detect
    shutil.rmtree(target, ignore_errors=True)


def test_idempotence_second_run_in_same_sandbox_does_not_duplicate(sim_workdir: Path) -> None:
    first = run_scenario("ssh-bruteforce-single-ip", seed=SEED, workdir=sim_workdir)
    second = run_scenario("ssh-bruteforce-single-ip", seed=SEED, workdir=sim_workdir)
    assert len(second.events) == len(first.events)
    assert len(second.incidents) == len(first.incidents)


def test_time_to_detect_bruteforce_within_one_engine_interval(all_results: dict[str, Any]) -> None:
    result = all_results["ssh-bruteforce-single-ip"]
    evaluation = evaluate(result)
    assert evaluation.time_to_detect is not None
    # The 5th failure occurs at t=40 s (10 s spacing); the matching medium tier
    # must fire at that cycle or the next 60 s engine cycle.
    assert 40 <= evaluation.time_to_detect <= 40 + 60


def test_report_math_and_wording(all_results: dict[str, Any]) -> None:
    results = list(all_results.values())
    evaluations = [evaluate(item) for item in results]
    summary = aggregate(evaluations)
    assert summary["scenarios"] == len(EXPECTED_IDS)
    assert summary["detected"] + summary["not_detected"] == len(EXPECTED_IDS)
    attacks = [item for item in evaluations if get_scenario(item.scenario_id).category == "attack"]
    assert 0.0 <= summary["detection_rate"] <= 1.0
    assert summary["detection_rate"] == sum(1 for item in attacks if item.detected) / len(attacks)
    markdown = render_markdown(results, summary)
    text = render_table(results, summary) + markdown
    assert (
        "Synthetic scenarios test rule behaviour, not real-world detection performance" in markdown
    )
    for banned in ("accuracy", "protects against", "attack confirmed"):
        assert banned not in text.lower()
    payload = json.loads(render_json(results))
    assert DISCLAIMER in payload["disclaimer"]
    assert "encrypted traffic" in payload["not_modelled"]
    assert payload["summary"]["scenarios"] == len(EXPECTED_IDS)
    assert len(payload["scenarios"]) == len(EXPECTED_IDS)


def test_per_scenario_explanations_in_markdown(all_results: dict[str, Any]) -> None:
    results = list(all_results.values())
    markdown = render_markdown(results, aggregate([evaluate(item) for item in results]))
    for result in results:
        assert result.scenario_id in markdown
        assert result.explanation, result.scenario_id


def test_safety_refuses_outside_and_system_workdirs() -> None:
    from scripts.simulator.runner import safe_workdir

    with pytest.raises(ValueError):
        safe_workdir("/tmp/outside")  # noqa: S108 - refusal test
    with pytest.raises(ValueError):
        safe_workdir("/etc/sim")
    with pytest.raises(ValueError):
        safe_workdir("/home/mouad/sim")


def test_safety_no_sockets_subprocess_or_external_writes(
    sim_workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    import psutil

    root = sim_workdir
    project = Path(__file__).resolve().parents[1]
    real_db = project / "sentinel.db"
    before_sandbox = _tree_hash(root)
    before_project = _project_hash(project)
    before_db = _file_state(real_db)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("simulator attempted a forbidden external operation")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(psutil, "Process", forbidden)
    monkeypatch.setattr(psutil, "net_connections", forbidden)
    monkeypatch.setattr(psutil, "process_iter", forbidden)

    real_open = builtins.open

    def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(flag in mode for flag in ("w", "a", "x", "+")) and isinstance(file, (str, Path)):
            path = Path(file).resolve()
            if path != root and root not in path.parents:
                raise AssertionError(f"simulator wrote outside its sandbox: {path}")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    for scenario in SCENARIOS:
        run_scenario(scenario.id, seed=SEED, workdir=root)
    assert any(root.iterdir())
    assert _tree_hash(root) != before_sandbox  # sandbox was written
    assert _project_hash(project) == before_project  # no project file changed
    assert _file_state(real_db) == before_db  # real DB untouched


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_file():
            digest.update(str(item.relative_to(path)).encode())
            digest.update(item.read_bytes())
    return digest.hexdigest()


_EXCLUDED_DIRS = {
    "sim_workdir",
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".next",
    "node_modules",
    "logs",
}


def _project_hash(project: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(project.rglob("*")):
        if any(part in _EXCLUDED_DIRS for part in item.parts) or item.suffix == ".pyc":
            continue
        if item.is_file():
            digest.update(str(item.relative_to(project)).encode())
            digest.update(item.read_bytes())
    return digest.hexdigest()


def _file_state(path: Path) -> tuple[int, int, str] | None:
    if not path.exists():
        return None
    return (
        path.stat().st_mtime_ns,
        path.stat().st_size,
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_dashboard_database_opens_through_real_api(sim_workdir: Path, monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    from api.main import create_app

    info = build_dashboard(seed=SEED, workdir=sim_workdir)
    monkeypatch.setenv("SENTINEL_SESSION_KEY", info["session_key"])
    app = create_app(db_path=str(info["db"]))
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json=info["credentials"])
        assert login.status_code == 200, login.text
        incidents = client.get("/api/incidents").json()["items"]
        assert incidents, "hidden attacks must be visible in the combined dashboard"
