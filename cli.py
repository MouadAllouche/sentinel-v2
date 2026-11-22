"""Sentinel command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from getpass import getpass
from pathlib import Path
from typing import Any

from core.config import load_settings
from core.export import export_events_csv, incident_report, render_incident
from core.health import get_health
from core.retention import DEFAULT_POLICY, plan_prune
from core.rules.backtest import backtest_rule
from engine.baselines import run_baselines
from engine.correlation import run_correlation
from engine.drift import accept_baseline, check_drift, init_drift
from engine.ingest import run_collection
from engine.logging_setup import setup_logging
from engine.rules import run_rules
from engine.runner import install_signal_handlers, run_engine_loop
from engine.scoring import run_scoring
from scripts.demo import DEFAULT_WORKDIR as DEFAULT_DEMO_WORKDIR
from scripts.demo import build_demo
from storage.auth_repository import create_user, list_users
from storage.database import init_db
from storage.drift_repository import (
    list_monitored_paths,
    reset_all_monitored_paths,
    seed_monitored_paths,
)
from storage.incident_repository import get_incident, list_incidents
from storage.repositories import get_setting, query_events
from storage.retention_repository import apply_prune, retention_stats
from storage.risk_repository import explain_score, get_assessment
from storage.rules_repository import (
    get_events_for_rules,
    list_rules,
    reset_rule,
    seed_rules,
    set_rule_enabled,
)
from storage.severity_repository import (
    get_defaults,
    reset_all_defaults,
    seed_defaults,
    set_default,
)

__all__ = ["main"]


def _emit(data: Any, as_json: bool, text: str) -> None:
    if as_json:
        print(json.dumps(data, default=str, sort_keys=True))
    else:
        print(text)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sentinel")
    parser.add_argument("--db")
    parser.add_argument("--config")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("init")
    sub.add_parser("api")
    sub.add_parser("collect")
    sub.add_parser("analyze")
    sub.add_parser("run")
    engine = sub.add_parser("engine")
    engine.add_argument("--once", action="store_true")
    engine.add_argument("--no-notify", action="store_true")
    seed = sub.add_parser("seed")
    seed.add_argument("--reset-all", action="store_true")
    drift = sub.add_parser("drift")
    drift.add_argument("action", choices=["init", "check", "accept"])
    drift.add_argument("path", nargs="?")
    sub.add_parser("baseline").add_argument("action", choices=["compute"])
    rules = sub.add_parser("rules")
    rules.add_argument("action", choices=["list", "show", "enable", "disable", "reset", "backtest"])
    rules.add_argument("identifier", nargs="?")
    rules.add_argument("--days", type=int, default=7)
    severity = sub.add_parser("severity")
    severity.add_argument("action", choices=["list", "set", "reset"])
    severity.add_argument("event_type", nargs="?")
    severity.add_argument("value", nargs="?")
    incidents = sub.add_parser("incidents")
    incidents.add_argument("action", choices=["list", "show"])
    incidents.add_argument("identifier", type=int, nargs="?")
    users = sub.add_parser("user")
    users.add_argument("action", choices=["create", "list", "disable", "set-password"])
    users.add_argument("--role", choices=["admin", "viewer"], default="viewer")
    prune = sub.add_parser("prune")
    prune.add_argument("--dry-run", action="store_true", help="no-op alias; dry-run is the default")
    prune.add_argument("--apply", action="store_true", help="actually delete prunable rows")
    export = sub.add_parser("export")
    export.add_argument("target")
    export.add_argument("identifier", type=int, nargs="?")
    export.add_argument("--format", default="md", choices=["md", "json", "pdf", "csv"])
    sub.add_parser("status")
    demo = sub.add_parser("demo")
    demo.add_argument("--reset", action="store_true")
    demo.add_argument("--live", action="store_true")
    demo.add_argument("--no-print-password", action="store_true")
    demo.add_argument("--workdir", help="demo workdir (default: demo_workdir/)")
    simulate = sub.add_parser("simulate")
    simulate.add_argument("action", choices=["list", "run", "dashboard", "live", "whatif"])
    simulate.add_argument("scenario", nargs="?")
    simulate.add_argument("--seed", type=int, default=0)
    simulate.add_argument("--format", choices=["table", "md", "json"], default="table")
    simulate.add_argument("--out")
    simulate.add_argument("--rules")
    simulate.add_argument("--speed", type=float, default=1.0)
    simulate.add_argument("--steps", type=int, default=5)
    return parser


def _simulate(args: Any) -> int:
    """Dispatch the sandboxed threat simulator commands (Phase 20)."""
    from scripts.simulator.evaluate import aggregate, evaluate
    from scripts.simulator.report import render_json, render_markdown, render_table, write_report
    from scripts.simulator.runner import (
        DEFAULT_WORKDIR,
        build_dashboard,
        run_all,
        run_scenario,
        simulate_live,
        whatif,
    )
    from scripts.simulator.scenarios import SCENARIOS

    action = args.action
    workdir = args.out
    if action == "list":
        for scenario in SCENARIOS:
            print(f"{scenario.id:32} {scenario.category:9} {scenario.title}")
        return 0
    if action == "run":
        target = args.scenario or "all"
        if target == "all":
            results = run_all(seed=args.seed, workdir=workdir)
        else:
            try:
                results = [run_scenario(target, seed=args.seed, workdir=workdir)]
            except ValueError as exc:
                print(str(exc))
                return 2
        summary = aggregate([evaluate(item) for item in results])
        text = (
            render_json(results)
            if args.format == "json"
            else render_markdown(results, summary)
            if args.format == "md"
            else render_table(results, summary)
        )
        print(text, end="")
        if args.out:
            write_report(results, fmt=args.format, out_dir=args.out)
        return 0
    if action == "dashboard":
        info = build_dashboard(seed=args.seed, workdir=workdir)
        print(f"Simulation dashboard: {info['db']}")
        print(f"Session key: {info['session_key']} (mode 0600)")
        sim_root = Path(workdir or DEFAULT_WORKDIR)
        print(
            f"Start the API: SENTINEL_SESSION_KEY=$(cat {sim_root / 'session.key'}) "
            f"SENTINEL_CONFIG={info['settings']} "
            "./venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000"
        )
        print("Start the web: cd web && npm run start")
        return 0
    if action == "live":
        return simulate_live(speed=args.speed, steps=args.steps, workdir=workdir)
    if action == "whatif":
        if not args.scenario or not args.rules:
            print("whatif requires a scenario and --rules FILE")
            return 2
        try:
            diff = whatif(args.scenario, args.rules, seed=args.seed, workdir=workdir)
        except ValueError as exc:
            print(str(exc))
            return 2
        print(
            f"findings gained: {', '.join(diff['findings_gained']) or 'none'}\n"
            f"findings lost: {', '.join(diff['findings_lost']) or 'none'}\n"
            f"severity changes: {diff['severity_changes']}\n"
            f"score change: {diff['score_change']}\n"
            f"time-to-detect change: {diff['time_to_detect_change']}"
        )
        if args.out:
            Path(args.out).mkdir(parents=True, exist_ok=True)
            (Path(args.out) / "whatif.json").write_text(
                json.dumps(diff, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv[1:])
    wants_json = "--json" in raw
    raw = [item for item in raw if item != "--json"]
    try:
        args = _parser().parse_args(raw)
    except SystemExit as exc:
        return int(exc.code or 2)
    args.json = args.json or wants_json
    db_path = args.db or str(Path("sentinel.db"))
    settings = (
        load_settings(config_path=args.config)
        if args.config
        else load_settings(env={"SENTINEL_DB_PATH": db_path, "SENTINEL_CONFIG": ""})
    )
    command = args.command
    if command == "api":
        import uvicorn

        uvicorn.run("api.main:app", host=settings.api.host, port=settings.api.port)
        return 0
    if command == "init":
        init_db(db_path)
        _emit({"ok": True}, args.json, f"initialised {db_path}")
        return 0
    if command == "collect":
        report = run_collection(settings, db_path)
        _emit(report.__dict__, args.json, f"events_new={report.events_new}")
        return 0
    if command in {"analyze", "run"}:
        if command == "run":
            run_collection(settings, db_path)
        run_rules(db_path)
        run_baselines(db_path)
        run_correlation(db_path)
        run_scoring(db_path)
        _emit({"ok": True}, args.json, "analysis complete")
        return 0
    if command == "engine":
        stop = {"requested": False}

        def _shutdown() -> bool:
            return bool(stop["requested"])

        install_signal_handlers()
        setup_logging(log_dir=settings.paths.log_dir)
        run_engine_loop(
            settings,
            db_path,
            once=args.once,
            no_notify=args.no_notify,
            shutdown=_shutdown,
        )
        return 0
    if command == "seed":
        seed_defaults(db_path)
        seed_rules(db_path)
        seed_monitored_paths(db_path)
        if args.reset_all:
            reset_all_defaults("cli", db_path)
            reset_all_monitored_paths("cli", db_path)
        _emit({"ok": True}, args.json, "seeded defaults")
        return 0
    if command == "drift":
        if args.action == "init":
            report = init_drift(db_path)
        elif args.action == "check":
            report = check_drift(db_path)
        else:
            match = next(
                (item for item in list_monitored_paths(db_path) if item.path == args.path), None
            )
            if match is None:
                return 1
            accept_baseline(match.id, "cli", "accepted via CLI", db_path)
            report = {"ok": True}
        _emit(report if isinstance(report, dict) else report.__dict__, args.json, "drift ok")
        return 0
    if command == "baseline":
        report = run_baselines(db_path)
        _emit(report.__dict__, args.json, f"baselines={report.baselines_stored}")
        return 0
    if command == "rules":
        if args.action == "list":
            rules = [rule.model_dump() for rule in list_rules(db_path=db_path)]
            _emit(rules, args.json, "\n".join(str(rule["id"]) for rule in rules))
            return 0
        identifier = args.identifier
        if not identifier:
            return 2
        if args.action == "show":
            rule = next((r for r in list_rules(db_path=db_path) if r.id == identifier), None)
            if rule is None:
                return 1
            _emit(rule.model_dump(), args.json, rule.name)
        elif args.action in {"enable", "disable"}:
            set_rule_enabled(identifier, args.action == "enable", "cli", db_path)
        elif args.action == "reset":
            reset_rule(identifier, "cli", db_path)
        elif args.action == "backtest":
            rule = next(
                (item for item in list_rules(db_path=db_path) if item.id == identifier), None
            )
            if rule is None:
                return 1
            end = datetime.now(UTC)
            start = end - timedelta(days=args.days)
            events = get_events_for_rules(start.isoformat(), db_path)
            result = backtest_rule(rule, events, start.isoformat(), end.isoformat())
            _emit(result.__dict__, args.json, f"findings={result.total_findings}")
        else:
            return 2
        return 0
    if command == "severity":
        defaults = get_defaults(db_path)
        if args.action == "list":
            _emit(
                {key: vars(value) for key, value in defaults.items()},
                args.json,
                "\n".join(sorted(defaults)),
            )
            return 0
        if args.action == "reset":
            reset_all_defaults("cli", db_path)
            return 0
        if args.event_type and args.value:
            existing = defaults.get(args.event_type)
            set_default(
                args.event_type,
                args.value,
                existing.points if existing else 0,
                actor="cli",
                db_path=db_path,
            )
            return 0
        return 2
    if command == "incidents":
        incidents = list_incidents(db_path=db_path)
        if args.action == "list":
            _emit(incidents, args.json, "\n".join(str(item["id"]) for item in incidents))
            return 0
        incident = next((item for item in incidents if item["id"] == args.identifier), None)
        if incident is None:
            return 1
        assessment = get_assessment("incident", incident["id"], db_path)
        _emit(
            {
                **incident,
                "assessment": assessment,
                "explanation": explain_score("incident", incident["id"], db_path),
            },
            args.json,
            incident["title"],
        )
        return 0
    if command == "user":
        if args.action == "create":
            password = getpass("New password: ")
            if len(password) < 12:
                return 2
            identifier = create_user(
                "admin" if args.role == "admin" else "viewer", password, args.role, db_path
            )
            _emit({"id": identifier}, args.json, f"created user {identifier}")
            return 0
        if args.action == "list":
            users = [
                {key: value for key, value in item.items() if key != "password_hash"}
                for item in list_users(db_path)
            ]
            _emit(users, args.json, "\n".join(str(item["username"]) for item in users))
            return 0
        return 2
    if command == "prune":
        policy = get_setting("retention", db_path) or DEFAULT_POLICY
        plan = plan_prune(policy, retention_stats(db_path, policy), datetime.now(UTC))
        result = apply_prune(
            plan,
            db_path,
            dry_run=not args.apply,
            actor="cli",
            policy=policy,
            now=datetime.now(UTC),
        )
        _emit(result, args.json, f"prune applied={result['applied']}")
        return 0
    if command == "export":
        if args.target == "incident" and args.identifier is not None:
            incident = get_incident(args.identifier, db_path)
            if incident is None:
                return 1
            data = incident_report(incident)
            rendered = render_incident(data, args.format)
            if isinstance(rendered, bytes):
                sys.stdout.buffer.write(rendered)
            else:
                print(rendered)
            return 0
        if args.target == "events":
            print(export_events_csv(query_events({}, db_path=db_path)["items"]), end="")
            return 0
        return 2
    if command == "status":
        health = get_health(db_path)
        _emit(health, args.json, health["status"])
        return 0
    if command == "simulate":
        return _simulate(args)
    if command == "demo":
        summary = build_demo(
            args.workdir or DEFAULT_DEMO_WORKDIR,
            reset=args.reset,
            print_password=not args.no_print_password,
            live=args.live,
        )
        _emit(summary, args.json, json.dumps(summary, sort_keys=True))
        return 0
    _emit({"error": f"unknown command: {command}"}, args.json, f"unknown command: {command}")
    return 2


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
