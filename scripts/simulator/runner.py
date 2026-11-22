"""Sandboxed scenario runner for the Phase 20 threat simulator."""

from __future__ import annotations

import base64
import json
import os
import random
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from collectors.filesystem import take_snapshot
from core.config import load_settings
from core.rules.models import validate_rule
from engine.drift import check_drift
from engine.ingest import run_collection
from engine.runner import default_steps, run_once
from scripts.simulator.feeds import FakeFeeds
from scripts.simulator.generators import SimulatedActivity
from scripts.simulator.scenarios import SCENARIOS, get_scenario
from storage.auth_repository import create_user, get_user_by_name
from storage.database import init_db
from storage.drift_repository import (
    add_monitored_path,
    get_previous_snapshot,
    list_monitored_paths,
    save_snapshot,
)
from storage.incident_repository import list_incidents
from storage.notification_repository import (
    add_channel,
    list_notifications,
    record_change,
)
from storage.repositories import (
    get_setting,
    query_events_bulk,
    set_setting,
)
from storage.rules_repository import (
    create_rule,
    get_rule,
    list_findings,
    update_rule,
)
from storage.severity_repository import add_allowlist_entry

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKDIR = ROOT / "sim_workdir"
BLOCKED = frozenset(
    {
        "etc",
        "var",
        "home",
        "root",
        "usr",
        "tmp",
        "dev",
        "proc",
        "sys",
        "boot",
        "opt",
        "bin",
        "sbin",
        "lib",
        "lib64",
        "mnt",
        "media",
        "srv",
    }
)
BASE_TIME = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def safe_workdir(path: str | Path) -> Path:
    """Refuse workdirs outside the project or inside a system directory."""
    resolved = Path(path).resolve()
    root = ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"simulator workdir must be inside the project: {resolved}")
    relative = resolved.relative_to(root)
    if any(part.lower() in BLOCKED for part in relative.parts):
        raise ValueError(f"simulator workdir may not be a system directory: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


@dataclass
class ScenarioResult:
    scenario_id: str
    seed: int
    events: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    incidents: list[dict[str, Any]] = field(default_factory=list)
    anomalies: list[dict[str, Any]] = field(default_factory=list)
    drift_events: list[dict[str, Any]] = field(default_factory=list)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    suppressed_count: int = 0
    explanation: str = ""
    first_malicious_at: datetime | None = None
    database: Path | None = None


def _write_settings(case: Path, db: Path, *, enable_feeds: bool) -> Path:
    target = case / "settings.toml"
    target.write_text(
        f"[paths]\n"
        f'database = "{db}"\n'
        f'auth_log = "{case / "auth.log"}"\n'
        f'dpkg_log = "{case / "dpkg.log"}"\n'
        f'log_dir = "{case / "logs"}"\n'
        f"\n[collectors]\n"
        f'auth_source = "auth_log"\n'
        f"network = {str(enable_feeds).lower()}\n"
        f"listening = {str(enable_feeds).lower()}\n"
        f"processes = {str(enable_feeds).lower()}\n"
        f"filesystem = false\ndpkg = true\nsystem = false\n"
        f"max_process_events_per_run = 50\n"
        f"\n[notifications]\nenabled = true\n"
        f"\n[drift]\nallow_custom_paths = true\n",
        encoding="utf-8",
    )
    return target


def _fake_key(seed: int) -> str:
    blob = base64.b64encode(f"simulation-key-{seed}".encode()).decode()
    return f"ssh-ed25519 {blob} simulator\n"


def _prepare_case(
    workdir: Path, scenario_id: str, activity: SimulatedActivity, seed: int
) -> tuple[Path, Path, Path, Any]:
    case = workdir / scenario_id
    case.mkdir(parents=True, exist_ok=True)
    etc = case / "etc"
    (etc / "cron.d").mkdir(parents=True, exist_ok=True)
    (case / "logs").mkdir(parents=True, exist_ok=True)
    sshd_file = etc / "sshd_config"
    if not sshd_file.exists():
        sshd_file.write_text("PermitRootLogin no\n", encoding="utf-8")
    key_file = etc / "authorized_keys"
    if not key_file.exists():
        key_file.write_text(_fake_key(seed), encoding="utf-8")
    cron_file = etc / "cron.d" / "backup"
    if not cron_file.exists():
        cron_file.write_text("# baseline\n", encoding="utf-8")
    # Standard persistence locations are part of the simulated host's normal
    # monitoring surface; all scenarios get the same baseline coverage.
    for directory in (etc / "systemd" / "system", etc / "profile.d"):
        directory.mkdir(parents=True, exist_ok=True)
    preload = etc / "ld.so.preload"
    if not preload.exists():
        preload.write_text("# baseline\n", encoding="utf-8")
    auth_log = case / "auth.log"
    dpkg_log = case / "dpkg.log"
    for path in (auth_log, dpkg_log):
        path.touch(exist_ok=True)
    db = case / f"{scenario_id}.db"
    init_db(db)
    settings_path = _write_settings(case, db, enable_feeds=True)
    settings = load_settings(config_path=settings_path)
    set_setting("notifications.enabled", True, updated_by="simulator", db_path=db)
    add_channel(
        {
            "name": "Simulation sink",
            "kind": "file",
            "enabled": True,
            "config": {"path": str(case / "logs" / "notifications.jsonl")},
            "min_severity": "high",
        },
        "simulator",
        db,
    )
    for ip in activity.allowlist_ips:
        add_allowlist_entry(
            {
                "kind": "ip",
                "value": ip,
                "scope": "suppress_alerts",
                "reason": "synthetic monitoring host",
                "enabled": True,
            },
            "simulator",
            db,
        )
    for path, kind, category in (
        (etc / "sshd_config", "file", "ssh"),
        (key_file, "authorized_keys", "authorized_keys"),
        (etc / "cron.d", "dir", "cron"),
        (etc / "systemd" / "system", "dir", "systemd"),
        (etc / "profile.d", "dir", "shell_profile"),
        (preload, "file", "ld_preload"),
    ):
        existing = next((item for item in list_monitored_paths(db) if item.path == str(path)), None)
        if existing is None:
            add_monitored_path(
                {
                    "path": str(path),
                    "kind": kind,
                    "category": category,
                    "sensitivity": "high",
                    "enabled": True,
                },
                "simulator",
                db,
                allow_custom_paths=True,
            )
        spec = next(item.as_spec() for item in list_monitored_paths(db) if item.path == str(path))
        if get_previous_snapshot(str(path), db) is None:
            snapshot, _warnings = take_snapshot(spec, now=BASE_TIME)
            save_snapshot(snapshot, is_baseline=True, db_path=db)
    # Historical lines are in the past and may be present at the first cycle.
    history = [line for _stamp, line in activity.history_lines]
    if history:
        with auth_log.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(history) + "\n")
    return case, db, settings_path, settings


def _apply_overrides(db: Path, overrides: list[dict[str, Any]]) -> None:
    for definition in overrides:
        validated, _warnings = validate_rule(definition)
        data = validated.model_dump(mode="json")
        identifier = str(data["id"])
        if get_rule(identifier, db_path=db) is None:
            create_rule(data, "simulator-whatif", db_path=db)
        else:
            update_rule(identifier, data, "simulator-whatif", db_path=db)


def _execute(
    scenario_id: str,
    seed: int,
    workdir: Path,
    *,
    overrides: list[dict[str, Any]] | None = None,
    full_steps: bool = False,
    replace_rules: bool = False,
) -> ScenarioResult:
    scenario = get_scenario(scenario_id)
    rng = random.Random(seed)  # noqa: S311 - deterministic simulation
    activity: SimulatedActivity = scenario.build(rng, BASE_TIME)
    case, db, _settings_path, settings = _prepare_case(workdir, scenario_id, activity, seed)
    allowed_rule_ids = {str(definition["id"]) for definition in (overrides or [])}
    if overrides:
        _apply_overrides(db, overrides)

    auth_log = case / "auth.log"
    dpkg_log = case / "dpkg.log"
    auth_index = dpkg_index = 0
    mutation_done: set[int] = set()
    feeds = FakeFeeds(activity.feeds)

    def collect(_settings: Any, _db: Any, now: datetime) -> dict[str, Any]:
        nonlocal auth_index, dpkg_index
        pending_auth = [line for stamp, line in activity.auth_lines if stamp <= now][auth_index:]
        pending_dpkg = [line for stamp, line in activity.dpkg_lines if stamp <= now][dpkg_index:]
        if pending_auth:
            with auth_log.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(pending_auth) + "\n")
            auth_index += len(pending_auth)
        if pending_dpkg:
            with dpkg_log.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(pending_dpkg) + "\n")
            dpkg_index += len(pending_dpkg)
        mutation_applied = False
        for index, mutation in enumerate(activity.mutations):
            if mutation.at <= now and index not in mutation_done:
                mutation_done.add(index)
                mutation_applied = True
                target = (case / mutation.path).resolve()
                if target != case.resolve() and case.resolve() not in target.parents:
                    raise ValueError(f"sandbox mutation escaped workdir: {mutation.path}")
                target.parent.mkdir(parents=True, exist_ok=True)
                if mutation.action == "create":
                    target.write_text(mutation.content, encoding="utf-8")
                elif mutation.action == "append_key":
                    target.write_text(
                        target.read_text(encoding="utf-8") + mutation.content, encoding="utf-8"
                    )
                elif mutation.action == "chmod_world_writable":
                    os.chmod(target, 0o666)  # noqa: S103 - sandbox file only
        with feeds.installed(now):
            report = run_collection(settings, db, now=now)
        drift_events = check_drift(db, now=now).drift_events if mutation_applied else 0
        return {"events_new": report.events_new, "drift_events": drift_events}

    base_steps = default_steps(settings, notify=True)

    # Always start with a seeding cycle so snapshot collectors establish a
    # baseline before injected feed records appear.
    times = {BASE_TIME}
    times.update(stamp for stamp, _ in activity.auth_lines)
    times.update(stamp for stamp, _ in activity.dpkg_lines)
    times.update(item.at for item in activity.mutations)
    times.update(item.at for item in activity.feeds)
    # Finish inside the hour after the last activity so the baseline cycle
    # evaluates that hour as the last completed hour.
    final = max(times, default=BASE_TIME) + timedelta(minutes=35)
    ordered = sorted(time for time in times if time >= BASE_TIME)
    # Coalesce idle simulated minutes: nothing happens between activity times,
    # and full pipeline cycles are expensive. Sampling keeps the same decisions
    # (all due activity is still fed at each sampled cycle) while bounding the
    # number of cycles so `simulate run all` stays fast.
    if len(ordered) > 40 and not full_steps:
        indices = sorted({round(index * (len(ordered) - 1) / 39) for index in range(40)})
        ordered = [ordered[index] for index in indices]

    def no_baseline(_s: Any, _db: Any, _now: Any) -> dict[str, Any]:
        return {"baselines": 0}

    def restrict_rules(_s: Any, _db: Any, _now: Any) -> dict[str, Any]:
        # run_once re-seeds defaults at the start of every cycle, so the
        # reference rule set is re-applied here immediately before evaluation.
        # Direct column update: set_rule_enabled re-validates whole definitions
        # and rejects reserved kinds whose stored shape needs extra fields.
        from contextlib import closing

        from storage.database import get_connection

        disabled = 0
        with closing(get_connection(db)) as connection, connection:
            for identifier, definition_json in connection.execute(
                "SELECT id, definition_json FROM rules WHERE enabled = 1"
            ):
                if identifier in allowed_rule_ids:
                    continue
                definition = json.loads(definition_json)
                definition["enabled"] = False
                connection.execute(
                    "UPDATE rules SET enabled = 0, definition_json = ? WHERE id = ?",
                    (json.dumps(definition, sort_keys=True, default=str), identifier),
                )
                disabled += 1
        return {"rules_disabled": disabled, "rules_kept": sorted(allowed_rule_ids)}

    for clock in ordered + [final]:
        # Baselines only change at hour boundaries or on the final cycle;
        # recomputing seven days of buckets every simulated minute is wasteful.
        run_baselines = clock.minute == 0 or clock == final
        steps = [
            (
                name,
                collect
                if name == "collect"
                else step
                if name != "baselines" or run_baselines
                else no_baseline,
            )
            for name, step in base_steps
        ]
        if replace_rules:
            rules_index = next(index for index, (name, _) in enumerate(steps) if name == "rules")
            steps.insert(rules_index, ("restrict-rules", restrict_rules))
        run_once(settings, db, clock, notify=True, steps=steps)

    events = query_events_bulk({}, db_path=db)
    result = ScenarioResult(
        scenario_id=scenario_id,
        seed=seed,
        events=events,
        findings=list_findings({}, db_path=db, limit=500),
        incidents=list_incidents(db_path=db),
        anomalies=[item for item in events if item.get("event_type") == "anomaly"],
        drift_events=[item for item in events if item.get("event_type") == "config_drift"],
        notifications=list_notifications(db_path=db),
        suppressed_count=sum(1 for item in events if item.get("allowlisted")),
        first_malicious_at=activity.malicious_from,
        database=db,
    )
    result.explanation = _explanation(result, scenario_id)
    return result


def _explanation(result: ScenarioResult, scenario_id: str) -> str:
    if result.findings:
        return str(result.findings[0].get("explanation") or result.findings[0].get("rule_id"))
    if result.anomalies:
        return str(result.anomalies[0].get("description"))
    if result.incidents:
        return str(result.incidents[0].get("summary") or result.incidents[0].get("title"))
    return f"No rule, anomaly or incident fired in the synthetic scenario {scenario_id}."


def run_scenario(
    scenario_id: str,
    *,
    seed: int = 0,
    workdir: str | Path | None = None,
    overrides: list[dict[str, Any]] | None = None,
    full_steps: bool = False,
    replace_rules: bool = False,
) -> ScenarioResult:
    return _execute(
        scenario_id,
        seed,
        safe_workdir(workdir or DEFAULT_WORKDIR),
        overrides=overrides,
        full_steps=full_steps,
        replace_rules=replace_rules,
    )


def run_all(*, seed: int = 0, workdir: str | Path | None = None) -> list[ScenarioResult]:
    target = safe_workdir(workdir or DEFAULT_WORKDIR)
    return [run_scenario(scenario.id, seed=seed, workdir=target) for scenario in SCENARIOS]


def whatif(
    scenario_id: str,
    rules_file: str | Path,
    *,
    seed: int = 0,
    workdir: str | Path | None = None,
) -> dict[str, Any]:
    try:
        overrides = json.loads(Path(rules_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid rule file: {exc}") from exc
    if not isinstance(overrides, list):
        raise ValueError("invalid rule file: expected a JSON list of rule definitions")
    for definition in overrides:
        validate_rule(definition)
    target = safe_workdir(workdir or DEFAULT_WORKDIR)
    base = run_scenario(scenario_id, seed=seed, workdir=target / "whatif-default")
    changed = run_scenario(
        scenario_id, seed=seed, workdir=target / "whatif-custom", overrides=overrides
    )
    from scripts.simulator.evaluate import evaluate

    base_evaluation = evaluate(base)
    changed_evaluation = evaluate(changed)
    base_ids = {(item.get("rule_id"), item.get("tier_index")) for item in base.findings}
    new_ids = {(item.get("rule_id"), item.get("tier_index")) for item in changed.findings}
    return {
        "scenario_id": scenario_id,
        "findings_gained": sorted(str(item[0]) for item in new_ids - base_ids),
        "findings_lost": sorted(str(item[0]) for item in base_ids - new_ids),
        "severity_changes": sum(
            1
            for a, b in zip(base.findings, changed.findings, strict=False)
            if a.get("severity") != b.get("severity")
        ),
        "score_change": sum(int(i.get("score") or 0) for i in changed.incidents)
        - sum(int(i.get("score") or 0) for i in base.incidents),
        "time_to_detect_change": (
            (changed_evaluation.time_to_detect or 0.0) - (base_evaluation.time_to_detect or 0.0)
        ),
    }


def build_dashboard(*, seed: int = 0, workdir: str | Path | None = None) -> dict[str, Any]:
    target = safe_workdir(workdir or DEFAULT_WORKDIR)
    result = run_scenario("mixed-realistic-week", seed=seed, workdir=target)
    combined = target / "sim.db"
    if result.database is None:
        raise RuntimeError("dashboard scenario produced no database")
    shutil.copy2(result.database, combined)
    username, password = "sim-admin", f"simulation-password-{seed:04d}-abcdef"
    if get_user_by_name(username, combined) is None:
        create_user(username, password, "admin", combined)
    key = f"simulation-session-key-{seed:08d}-abcdefghijklmnopqrstuvwxyz"
    key_path = target / "session.key"
    descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(key + "\n")
    os.chmod(key_path, 0o600)
    credentials = {"username": username, "password": password}
    credentials_path = target / "credentials.json"
    descriptor = os.open(credentials_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(credentials, handle)
    os.chmod(credentials_path, 0o600)
    return {
        "db": combined,
        "session_key": key,
        "credentials": credentials,
        "workdir": target,
        "settings": target / "mixed-realistic-week" / "settings.toml",
    }


def simulate_live(*, speed: float = 1.0, steps: int = 5, workdir: str | Path | None = None) -> int:
    """Append synthetic lines gradually so the dashboard live feed can update.

    This is the only simulator command that may sleep in real time (spec 20.1).
    It is bounded by ``--steps`` and stops cleanly on Ctrl+C.
    """
    import time

    target = safe_workdir(workdir or DEFAULT_WORKDIR)
    seed_rng = random.Random(0)  # noqa: S311 - deterministic simulation
    activity = get_scenario("mixed-realistic-week").build(seed_rng, BASE_TIME)
    # If a dashboard DB was built, feed that exact log and publish change rows
    # so the dashboard's SSE/polling live updates actually fire.
    sim_db = target / "sim.db"
    dashboard_case = target / "mixed-realistic-week"
    settings_path = dashboard_case / "settings.toml"
    use_dashboard = sim_db.exists() and settings_path.exists()
    settings = load_settings(config_path=settings_path) if use_dashboard else None
    auth_log = (
        Path(str(get_setting("auth_log", sim_db) or dashboard_case / "auth.log"))
        if use_dashboard
        else target / "live" / "auth.log"
    )
    auth_log.parent.mkdir(parents=True, exist_ok=True)
    auth_log.touch(exist_ok=True)
    already = set(auth_log.read_text(encoding="utf-8").splitlines())
    try:
        for line in [line for _stamp, line in activity.auth_lines[:steps]]:
            if line in already:
                continue
            with auth_log.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            if use_dashboard and settings is not None:
                with FakeFeeds([]).installed(BASE_TIME):
                    run_collection(settings, sim_db, now=BASE_TIME)
                record_change("cycle.completed", 0, db_path=sim_db)
            if speed > 0:
                time.sleep(min(1.0, 1.0 / speed))
    except KeyboardInterrupt:
        return 0
    return 0
