# SENTINEL — MASTER PROMPT (v2)

You are a senior engineer (Python backend, security tooling, TypeScript/Next.js) building **Sentinel** from an empty folder to a finished, tested, documented, demonstrable product. This file holds the architecture and global specifications. Each phase has its own detailed spec in `specs/NN-name.md`; read the matching spec **before** starting that phase. Also read `AGENTS.md` (rules) and load `sentinel-*` skills when their descriptions match your task.

---

## 1. Mission

Sentinel monitors **one Linux server** (the machine it runs on). It collects security evidence, normalizes it into one event format, stores it in SQLite, applies **user-defined rules**, correlates related events into incidents with explained timelines, learns behavioral baselines, detects configuration drift and persistence mechanisms, scores risk with transparent rules, notifies the administrator, and presents everything in a Next.js dashboard where the administrator can edit rules, default severities, allowlists and more.

Central principle: **Sentinel collects evidence, organizes it, connects related events, detects deviations, and explains security risks to the administrator.**

### Four core functions
1. **Incident reconstruction and attack timeline**: group related events by shared attributes (IP, username, process, rule evidence) within configurable windows; keep every link with its reason and strength; chronological timeline; separate observed facts from inference; MITRE ATT&CK indicative mapping; status workflow and analyst notes.
2. **Behavioral baselines**: hourly zero-filled statistics over a configurable window; anomaly detection with explanations (metric, observed, mean, std, how far above); maturity gates; per-metric editable thresholds.
3. **Configuration drift and persistence monitoring**: files and directories (hash, owner, group, mode, mtime, size; key fingerprints for `authorized_keys`; entry listings for directories such as cron/systemd); exact change descriptions; explicit baseline approval; never modifies anything.
4. **Explainable risk prioritization**: one transparent rule engine drives alerts **and** scoring; every score stores its reasons and evidence; no double counting.

### User-controllable behavior (key requirement)
- **Rules**: the user defines detection rules in the UI/API, e.g. "failed logins from one IP: ≥5 within 10 minutes → medium; ≥20 within 10 minutes → high; ≥50 within 60 seconds → critical". Rule kinds: threshold (with tiers, windows, group-by, distinct counts), sequence, new-value, field-match, baseline-metric, incident-meta. Rules are versioned, enable/disable-able, backtestable against history, resettable to defaults.
- **Default event severities**: every event type has a default severity and base points; conditional **severity overrides** refine them (e.g. failed login for `root` → medium). All editable, with "reset to default" and an explicit "re-apply to existing events" action.
- **Allowlist / suppressions** with reasons and expiry; suppressed evidence is stored and shown, never silently dropped.

### Safety and scope (non-negotiable)
Single host · no packet inspection · **no automatic remediation** · **read-only toward the monitored system** · no ML · explainable rules and basic statistics · evidence-based wording · least privilege (dedicated unprivileged user in group `adm`; never root) · `/etc/shadow` metadata only · no file contents, no command lines, no secrets stored · outbound traffic only through explicitly enabled notification channels.

---

## 2. Architecture

```
┌────────────────────────────── Linux server ──────────────────────────────┐
│ auth.log / journald · dpkg.log · net connections · listening ports ·     │
│ processes · monitored files & dirs · system info                         │
└──────────────┬────────────────────────────────────────────────────────────┘
               ▼
 collectors/   (read-only, per-item error handling, state diffing)
               ▼
 core/ (PURE)  normalizer → severity resolver → allowlist → enrichment
               ▼
 storage/      SQLite: events (+promoted columns), state, runs
               ▼
 core/rules/   threshold · sequence · new_value · field_match · baseline_metric
               → rule findings + `rule_triggered` events
               ▼
 core/         correlation → incidents → incident_meta rules → risk scoring
               ▼
 engine/       scheduler loop · retention · notifications · exports
               ▼
 api/          FastAPI (auth, RBAC, CSRF, REST, SSE, OpenAPI)
               ▼
 web/          Next.js dashboard (same-origin proxy to the API)
```

Processes: `python cli.py engine` (collection + analysis loop), `uvicorn api.main:app` (API, 127.0.0.1:8000), `next start` (web, 127.0.0.1:3000, proxies `/api/*` to the API). All three are independent; SQLite WAL mode lets them share the database.

### Layering rules
- `core/` is pure: no DB, filesystem, clock, network or environment access. It takes dataclasses/dicts + an injected `now`, returns results.
- `storage/` is the only place with SQL. `collectors/` the only place that reads system state. `engine/` orchestrates. `api/` is thin: validate → call → serialize. `web/` never contains security logic; it renders what the API returns and edits configuration via the API.

---

## 3. Repository structure (final shape; create modules when their phase arrives)

```
sentinel/
├── AGENTS.md  SENTINEL_MASTER_PROMPT.md  PROGRESS.md  README.md
├── pyproject.toml  Makefile  .env.example  .gitignore
├── .github/workflows/ci.yml
├── cli.py
├── config/settings.toml
├── core/
│   ├── config.py timeutil.py events.py normalizer.py severity.py conditions.py
│   ├── allowlist.py enrichment.py mitre.py
│   ├── rules/ {models.py threshold.py sequence.py new_value.py
│   │           field_match.py baseline_metric.py incident_meta.py defaults.py engine.py backtest.py}
│   ├── correlation.py incidents.py timeline.py
│   ├── baseline.py anomaly_detection.py
│   ├── drift_detection.py
│   ├── risk_scoring.py
│   ├── notifications/ {models.py throttle.py render.py}
│   ├── retention.py export.py auth.py
│   └── pipeline.py
├── collectors/ {logs.py journald.py dpkg.py network.py listening.py processes.py filesystem.py system.py}
├── storage/ {database.py migrations.py repositories.py}
├── engine/ {runner.py scheduler.py notifier.py logging_setup.py}
├── api/
│   ├── main.py deps.py security.py schemas.py sse.py
│   └── routers/ {auth events incidents rules severity allowlist baselines drift notifications system users audit filters}.py
├── web/                      # Next.js app (see spec 13-17)
├── deploy/ {sentinel-engine.service sentinel-api.service sentinel-web.service}.example
├── scripts/ {demo.py generate_attack_vm.md}
├── specs/  docs/  sample_data/
└── tests/ {unit integration api fuzz conftest.py}
```

---

## 4. Global specifications

### 4.1 Event format
Required: `timestamp`, `source`, `event_type`, `severity`, `description`. Optional (only when known): `username`, `source_ip`, `local_ip`, `destination_ip`, `destination_port`, `connection_status`, `process_id`, `process_name`, `user_permissions` (`{before:[str], after:[str]}`), `file_path`, `details` (dict), `enrichment` (dict), `severity_source` (`default` | `override:<id>` | `rule:<id>`).

**Event types**: `failed_login`, `successful_login`, `invalid_user`, `preauth_disconnect`, `sudo_command`, `su_command`, `user_created`, `user_deleted`, `group_member_added`, `password_changed`, `permission_change`, `network_connection`, `new_listening_port`, `process_started`, `suspicious_process`, `package_installed`, `package_removed`, `config_drift`, `anomaly`, `rule_triggered`, `system_info`.
**Sources**: `auth_log`, `journald`, `dpkg`, `network`, `listening`, `process`, `filesystem`, `system`, `baseline`, `rules`.

IP fields: `source_ip` = remote initiator (SSH client). `local_ip` = this host. `destination_*` = remote end of outbound traffic. Never mix.

Validation (`validate_event`): dict; required fields present; `source/event_type/description` non-empty strings; severity valid; timestamp parses with `fromisoformat`; optional text fields are strings; `destination_port`/`process_id` ints; `details`/`enrichment` dicts; `user_permissions` dict with list-of-str `before`/`after`. Validation tolerates naive timestamps; `normalize_event` always outputs UTC-aware; storage rejects naive.

Normalizer aliases: `timestamp←time|date`, `source←source_system`, `event_type←action|event`, `severity←level`, `description←message`, `username←user|account`, `source_ip←ip|ip_address`, `process_name←process`, `user_permissions←permissions`. Event-type aliases: `login_failure|failed_password→failed_login`, `login_success→successful_login`, `permission_modified|privilege_escalation→permission_change`. Unknown fields dropped.

### 4.2 Time
`core/timeutil.py`: `utc_now()`, `to_utc_iso()`, `parse_ts()`. All stored timestamps UTC `+00:00`. Naive input = server-local time (configurable). Time-dependent code takes `now`.

### 4.3 Configuration split
- **`config/settings.toml` (static/bootstrap)**: paths (database, auth_log, dpkg_log, log dir), collector toggles and intervals, journald options, API bind host/port, session lifetime, engine intervals, feature flags (notifications globally on/off, default off). Env overrides: `SENTINEL_CONFIG`, `SENTINEL_DB_PATH`, `SENTINEL_SESSION_KEY`.
- **Database (`app_settings` + dedicated tables), user-editable via UI**: rules, event-type defaults, severity overrides, allowlist, monitored paths, risk severity thresholds, baseline parameters, notification channels/routes, retention policy, users. All seeded from `core/rules/defaults.py` and `core/severity.py` defaults; each item remembers its `default_definition` for reset.

### 4.4 Database
SQLite, WAL, `foreign_keys=ON`, `busy_timeout=5000`. Migrations: `schema_version` + ordered idempotent migration functions; each phase appends exactly one. Every storage function takes optional `db_path`. All SQL parameterised. Tables (phase in brackets):

| Table | Key columns |
|---|---|
| `events` [2] | `id`, `timestamp`, `source`, `event_type`, `severity`, `severity_source`, `username`, `source_ip`, `process_name`, `destination_ip`, `file_path` (promoted, nullable, indexed), `event_hash` UNIQUE, `event_data` JSON, `allowlisted` 0/1, `ingested_at` |
| `collector_state` [2] | `key` PK, `value_json`, `updated_at` |
| `collector_runs` [3] | `id`, `collector`, `started_at`, `finished_at`, `events_found`, `events_new`, `status`, `message` |
| `audit_log` [2] | `id`, `ts`, `actor`, `action`, `target_type`, `target_id`, `before_json`, `after_json`, `ip` |
| `event_type_defaults` [4] | `event_type` PK, `severity`, `points`, `enabled`, `description`, `default_severity`, `default_points` |
| `severity_overrides` [4] | `id`, `name`, `priority`, `conditions_json`, `severity`, `enabled`, `builtin`, `default_definition_json` |
| `allowlist_entries` [4] | `id`, `kind`, `value`, `scope`, `reason`, `expires_at`, `created_by`, `created_at`, `enabled` |
| `rules` [5] | `id` (slug), `name`, `kind`, `enabled`, `builtin`, `version`, `definition_json`, `default_definition_json`, `created_at`, `updated_at` |
| `rule_versions` [5] | `rule_id`, `version`, `definition_json`, `changed_by`, `changed_at` |
| `rule_findings` [5] | `id`, `rule_id`, `rule_version`, `group_key`, `tier_index`, `severity`, `points`, `window_start`, `window_end`, `observed`, `evidence_event_ids_json`, `created_at`, UNIQUE(`rule_id`,`group_key`,`tier_index`,`window_start`) |
| `incidents` [7] | `id`, `correlation_key` UNIQUE, `title`, `status`, `merged_into`, `first_seen`, `last_seen`, `primary_ip`, `primary_username`, `severity`, `risk_score`, `summary`, `mitre_json`, `assignee`, timestamps |
| `incident_events` [7] | `incident_id`, `event_id`, `relation_reason`, `link_strength`, PK(both) |
| `incident_notes` [7] | `id`, `incident_id`, `author`, `body`, `created_at` |
| `incident_status_history` [7] | `id`, `incident_id`, `from_status`, `to_status`, `actor`, `reason`, `at` |
| `baselines` [8] | `id`, `metric`, `subject`, `bucket`, `window_start`, `window_end`, `mean`, `stddev`, `sample_count`, `computed_at`, UNIQUE(metric,subject,window_start,window_end) |
| `monitored_paths` [9] | `id`, `path` UNIQUE, `kind` (file/dir/authorized_keys), `sensitivity`, `category`, `metadata_only`, `enabled`, `recursive`, `max_entries` |
| `file_snapshots` [9] | `id`, `path`, `exists_flag`, `sha256`, `owner`, `group_name`, `mode`, `mtime`, `size`, `extra_json`, `captured_at`, `is_baseline` |
| `risk_assessments` [10] | `id`, `target_type`, `target_id`, `score`, `severity`, `reasons_json`, `computed_at`, UNIQUE(target_type,target_id) |
| `notification_channels` [11] | `id`, `name`, `kind` (webhook/email/telegram), `enabled`, `config_json` (env-var names only), `min_severity`, `filters_json`, `throttle_json` |
| `notification_log` [11] | `id`, `channel_id`, `incident_id`, `finding_id`, `sent_at`, `status`, `detail` |
| `users` [12] | `id`, `username` UNIQUE, `password_hash`, `role` (admin/viewer), `disabled`, `failed_logins`, `locked_until`, `created_at` |
| `sessions` [12] | `id_hash` PK, `user_id`, `created_at`, `last_seen`, `expires_at`, `ip`, `user_agent` |
| `saved_filters` [12] | `id`, `user_id`, `name`, `page`, `query_json` |
| `app_settings` [4+] | `key` PK, `value_json`, `updated_at`, `updated_by` |

`event_hash` = SHA-256 of canonical JSON (`sort_keys`, compact separators, `default=str`) of the normalized event **excluding** `severity`, `severity_source`, `enrichment`.

### 4.5 Rule model (summary; full spec in `specs/05`, `specs/06`)
A rule is a validated JSON document: `{id, name, description, kind, enabled, match, group_by, aggregate, tiers[], window_mode, cooldown_seconds, actions, scope, mitre}` plus kind-specific fields. A **tier** is `{count, window_seconds, severity, points, label}`. Highest satisfied tier wins per group and window; escalation to a higher tier re-fires, repeats of the same tier are suppressed by cooldown and by the unique key. Evaluators are pure functions: `evaluate(rule, events, now) -> list[Finding]`.

### 4.6 Severity resolution order (summary; full spec in `specs/04`)
`allowlist flag (annotation only)` → first matching enabled **override** by priority → **event-type default** → built-in fallback `low`. Rule findings carry their own tier severity. Incident severity = max(score-based severity, highest finding severity in the incident).

### 4.7 Security model (API/UI)
Local users with roles `admin` / `viewer`; scrypt password hashes; httpOnly SameSite=Strict session cookie; CSRF double-submit token on unsafe methods; login rate-limit and lockout; every mutation audited; API and web bind to `127.0.0.1`; `Content-Security-Policy` and security headers on the web app; secrets only from env. Details in `specs/12` and skill `sentinel-security-hardening`.

### 4.8 Tooling
`pyproject.toml` (project metadata, `requires-python = ">=3.12"`, ruff, mypy, pytest config), `Makefile`, `.env.example`, GitHub Actions CI (Python job: ruff, mypy, pytest with coverage; Web job: lint, typecheck, vitest, build, Playwright against a seeded demo DB), `pytest.ini`-equivalent in `pyproject.toml` with `pythonpath = ["."]`.

---

## 5. Phases (each has a spec file; read it first)

| # | Spec | Deliverable |
|---|---|---|
| 0 | `specs/00-bootstrap.md` | repo, tooling, config, timeutil, CI skeleton |
| 1 | `specs/01-events-normalizer.md` | validation, normalizer, event taxonomy |
| 2 | `specs/02-storage.md` | SQLite schema v1, migrations, repositories, audit log |
| 3 | `specs/03-collectors-ingestion.md` | all collectors, ingestion, fuzz tests |
| 4 | `specs/04-severity-allowlist-enrichment.md` | editable defaults/overrides, allowlist, enrichment |
| 5 | `specs/05-rules-engine-core.md` | rule models, conditions, threshold evaluator, backtest |
| 6 | `specs/06-rules-engine-advanced.md` | sequence, new-value, field-match, seeded default rules |
| 7 | `specs/07-correlation-incidents.md` | correlation, incidents, timeline, workflow, MITRE |
| 8 | `specs/08-baselines-anomalies.md` | baselines, baseline-metric rules, anomalies |
| 9 | `specs/09-config-drift.md` | files, dirs, persistence, authorized_keys |
| 10 | `specs/10-risk-scoring.md` | incident-meta rules, scoring, recency decay |
| 11 | `specs/11-pipeline-engine-ops.md` | pipeline, engine loop, CLI, retention, notifications, exports, logging |
| 12 | `specs/12-api.md` | FastAPI, auth, RBAC, CSRF, SSE, OpenAPI |
| 13 | `specs/13-web-foundation.md` | Next.js scaffold, API client, auth, layout, design system |
| 14 | `specs/14-web-overview-events.md` | overview, events explorer |
| 15 | `specs/15-web-incidents.md` | incident list/detail, timeline, graph, workflow, export |
| 16 | `specs/16-web-rules-severity.md` | rule builder, backtest, severities, allowlist |
| 17 | `specs/17-web-behavior-drift-admin.md` | behavior, drift, notifications, settings, users, audit, health |
| 18 | `specs/18-demo-e2e-deploy.md` | demo, integration + e2e tests, deployment docs |
| 19 | `specs/19-final-audit.md` | audit against definition of done |

---

## 6. Working protocol

**First turn only** (no code): reply with (a) a 15-line summary of your understanding, (b) the default decisions you will take, (c) contradictions, risks or gaps you see in the specs, (d) the exact versions of Node, npm, Python and Next.js you detect or plan to use. Do not ask questions unless truly blocked. Then execute **Phase 0** only.

**For every phase**
1. Read `specs/NN-*.md` and load relevant skills. State your plan and the tests you will write.
2. Write tests first; watch them fail for the right reason; implement; make them pass.
3. Run the **entire** suite (Python and, once it exists, web tests); run `make lint`.
4. Run `/review N` (the `reviewer` subagent); fix all blockers.
5. Update `PROGRESS.md` and `docs/DECISIONS.md`; commit `phase-N: summary`.
6. Report exactly: **Done** (files) · **Tests** (paste summary lines) · **Reviewer findings and fixes** · **Decisions/deviations** · **Risks/open issues** · **Next** (first three actions). Then stop.

**Rules**: no stubs; no unrequested features or dependencies; small, typed, documented functions; no global mutable state; fix causes not tests; if a spec is wrong, say so and propose a fix before changing it; degrade gracefully on permissions; never escalate.

## 7. Definition of done
- Python tests (unit, integration, api, fuzz) and web tests (Vitest, Playwright) pass; CI config passes locally.
- Running collect/analyze repeatedly is idempotent.
- Every incident shows timeline, grouping reasons, and score reasons; every finding shows rule, tier, evidence.
- Users can create/edit/disable/backtest rules, edit default severities and overrides, manage allowlist, and reset any of them to defaults, from the UI; all audited.
- No automatic remediation; no secrets/contents/command lines stored; nothing writes outside the project or to monitored paths.
- Docs match the code; `PROGRESS.md` fully checked with evidence; demo reproducible from a fresh clone.
