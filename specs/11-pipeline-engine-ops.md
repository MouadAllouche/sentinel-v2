# Phase 11 — Pipeline, engine daemon, CLI, retention, notifications, exports, logging

Skills: sentinel-ops-deployment, sentinel-security-hardening, sentinel-rules-engine, sentinel-sqlite-patterns, sentinel-testing-workflow.

## Goal
Run everything continuously and safely: one analysis pipeline, a scheduler-driven engine, a CLI, data retention, notifications, exports and structured logging with self-monitoring.

## 11.1 Pipeline — `core/pipeline.py` + `engine/runner.py`
`run_cycle(settings, db_path, now=None) -> CycleReport` executes, in order, each step isolated (a failing step is logged, recorded and does not stop others):
1. `collect` (Phase 3 incl. drift check from Phase 9 as the `filesystem` collector)
2. `severity+allowlist` already applied at ingest; no step needed
3. `rules` — load enabled rules, evaluate threshold/sequence/new_value/field_match over the needed event window, save findings, emit `rule_triggered` events
4. `baselines+anomalies` — compute, evaluate baseline-metric rules, emit anomaly events/findings
5. `correlate` — events (+ rule_triggered) → components → `plan_incidents` → apply
6. `score` — incident-meta rules, scoring, persist, severity-change records
7. `notify` — enqueue notifications for new/escalated incidents and qualifying findings
8. `publish` — push change notifications to the SSE hub (Phase 12) via a lightweight `changes` table or in-process queue
`CycleReport`: per step `{status, duration_ms, counts, warnings, error}`; persisted in `collector_runs`-style table `cycle_runs` (add to `m009`). Cycle lock: a lock row/file prevents two engines running concurrently; stale locks expire.

## 11.2 Engine daemon — `engine/runner.py`, `engine/scheduler.py`
`python cli.py engine` loops: collection every `collect_interval_seconds`, analysis every `analyze_interval_seconds`, retention daily, graceful shutdown on SIGTERM/SIGINT (finish current step, release lock), jitter to avoid lockstep, backoff when a step errors repeatedly, `--once` for a single cycle, `--no-notify`. `now` injectable; scheduler logic is a pure state machine (`next_due(state, now)`) so it is unit-testable without sleeping.

## 11.3 CLI — `cli.py` (argparse, subcommands, exit codes 0/1/2)
`init` · `collect` · `analyze` · `run` (collect+analyze once) · `engine [--once]` · `seed [--reset-all]` · `drift init|check|accept <path>` · `baseline compute` · `rules list|show|enable|disable|reset|backtest <id> --days N` · `severity list|set <type> <sev>|reset` · `incidents list|show <id>` · `user create|list|disable|set-password` (password prompted with `getpass`, never as an argument; min 12 chars) · `prune [--dry-run]` · `export incident <id> --format md|json|pdf` · `status` (health summary) · `demo` · global `--db`, `--config`, `--json`.

## 11.4 Retention — `core/retention.py` (pure planning) + storage
Policy in `app_settings` (`retention`), editable, validated:
```json
{ "events": {"low_days": 14, "medium_days": 60, "high_days": 365, "critical_days": 365},
  "findings_days": 365, "snapshots_keep_per_path": 200, "collector_runs_days": 30, "cycle_runs_days": 14,
  "notification_log_days": 90, "audit_days": 730, "sessions_expired_days": 7, "vacuum": true }
```
Rules: events linked to an incident that is not `closed`/`false_positive`-older-than-policy are **never** pruned; baselines needed for the current window are never pruned; audit rows are pruned last and only past `audit_days`; every prune run is itself audited with counts. `plan_prune(policy, stats, now) -> PrunePlan` (pure) → `apply_prune(plan)`; `--dry-run` default in the CLI/API; `VACUUM` only when explicitly enabled and not while the API holds long reads (use `PRAGMA wal_checkpoint(TRUNCATE)` + `incremental_vacuum` if configured).

## 11.5 Notifications — `core/notifications/*`, `engine/notifier.py`
Off by default (global kill switch `notifications.enabled=false` in settings **and** per-channel `enabled`). Channels (DB, admin-editable): `webhook` (JSON POST, HMAC-SHA256 signature header using a secret read from the env var **named** in the channel), `email` (SMTP via `smtplib`, STARTTLS required unless explicitly `allow_insecure`), `telegram` (bot token from env var name + chat id).
- Routing: `min_severity`, event/finding filters (rule ids, tags, incident severity changes only), quiet hours (optional), per-incident **cooldown** and global **rate limit** (`throttle_json`: `max_per_hour`, `cooldown_minutes`, `digest_minutes` optional digest mode combining several incidents).
- Triggers: incident created at/above `min_severity`; incident **escalated** (severity increased); finding with `actions.notify=true` at/above `min_severity` (when not part of an incident already notified); never for `false_positive`/`closed`/suppressed (allowlisted) evidence.
- Message rendering (`core/notifications/render.py`, pure): subject/title with severity, incident title, score, top 3 reasons, first/last seen, link to the dashboard (`base_url` setting), and the caveat "Automated correlation; verify before acting". **No file contents, no secrets, no command arguments.**
- Delivery in `engine/notifier.py` with `httpx`/`smtplib` behind a `Transport` interface; retries with exponential backoff (max 3), timeouts (5 s), records `notification_log` (status, detail, never secrets); failures never break the cycle.
- `POST /api/notifications/{id}/test` sends a clearly marked test message. Tests use fake transports only; **no test performs real network I/O**.

## 11.6 Exports — `core/export.py`
`incident_report(incident_id) -> dict` (single source) rendered to: **Markdown** (summary, severity/score with reasons, timeline with observed/inferred labels, grouping reasons, evidence table, MITRE, notes, status history, caveats), **JSON** (full machine-readable), **PDF** (`reportlab`, same sections, no external fonts/network). Events export streams CSV/JSON (`export_events(filters)` generator; hard cap 100 000 rows; formula-injection protection: prefix cells starting with `= + - @` with `'`). Exports never include secrets (there are none stored) and always include the generation time and Sentinel version.

## 11.7 Logging and self-monitoring — `engine/logging_setup.py`
Python `logging` with JSON formatter, rotating file in `log_dir` (10 MB × 5), console handler; fields: `ts, level, component, event, request_id?, duration_ms?`; redaction filter (drops values for keys matching `password|secret|token|authorization|cookie`). Metrics kept in DB for the dashboard: last cycle status, per-collector last run/status/warnings, DB size, event count, oldest event, queue lag. `core.health.get_health(db_path) -> dict` (used by CLI `status` and `/api/health`): `ok|degraded|down` with reasons (e.g. engine not seen for 3× interval, auth.log unreadable).

## 11.8 Migrations
`m009`: `cycle_runs`, `notification_channels`, `notification_log`, `changes` (id, kind, ref_id, at) for SSE, saved indexes.

## Worked example
`python cli.py demo` is not built yet; instead: seed the standard scenario events via a fixture, run `run_cycle` twice. Expected: second run reports zero new events/findings/incidents/notifications; `incidents show 1 --json` returns the timeline and reasons; a webhook channel (fake transport) with `min_severity=high` received exactly **one** message (escalation to critical later produces exactly one more).

## Tests
Cycle ordering and isolation (inject a failing step); lock behavior; scheduler pure-state tests (due times, jitter bounds, backoff, shutdown flag); CLI commands via `main(argv)` with tmp DB (including exit codes, `--json`, password never in argv — prompt monkeypatched); retention planning (never prune linked/open evidence, per-severity ages, dry-run default, audit row); notifications: routing matrix (severity × channel × filters), cooldown, rate limit, digest, escalation-only, quiet hours, suppression, secrets absent from rendered text and logs, retry/backoff with fake clock, transport failure isolation, HMAC signature correctness, global kill switch; exports: Markdown/JSON/PDF generated (PDF header bytes, page text contains title and score), CSV injection protection, caps; logging redaction; health states; idempotent full cycle.

## Gate
Green suite; `python cli.py run` works locally; `python cli.py engine --once` exits 0; `docs/OPERATIONS.md` started.
