# Progress

Phases are completed one at a time. "Evidence" names the files and test names that
satisfy each gate. Status legend: ✅ done · ⬜ not started.

| # | Spec | Deliverable | Status | Evidence |
|---|---|---|---|---|
| 0 | `specs/00-bootstrap.md` | repo, tooling, config, timeutil, CI skeleton | ✅ | see below |
| 1 | `specs/01-events-normalizer.md` | validation, normalizer, event taxonomy | ✅ | see below |
| 2 | `specs/02-storage.md` | SQLite schema v1, migrations, repositories, audit log | ✅ | see below |
| 3 | `specs/03-collectors-ingestion.md` | all collectors, ingestion, fuzz tests | ✅ | see below |
| 4 | `specs/04-severity-allowlist-enrichment.md` | editable defaults/overrides, allowlist, enrichment | ✅ | see below |
| 5 | `specs/05-rules-engine-core.md` | rule models, conditions, threshold evaluator, backtest | ✅ | see below |
| 6 | `specs/06-rules-engine-advanced.md` | sequence, new-value, field-match, seeded default rules | ✅ | see below |
| 7 | `specs/07-correlation-incidents.md` | correlation, incidents, timeline, workflow, MITRE | ✅ | see below |
| 8 | `specs/08-baselines-anomalies.md` | baselines, baseline-metric rules, anomalies | ✅ | see below |
| 9 | `specs/09-config-drift.md` | files, dirs, persistence, authorized_keys | ✅ | see below |
| 10 | `specs/10-risk-scoring.md` | incident-meta rules, scoring, recency decay | ✅ | see below |
| 11 | `specs/11-pipeline-engine-ops.md` | pipeline, engine loop, CLI, retention, notifications, exports, logging | ✅ | see below |
| 12 | `specs/12-api.md` | FastAPI, auth, RBAC, CSRF, SSE, OpenAPI | ✅ | see below |
| 13 | `specs/13-web-foundation.md` | Next.js scaffold, API client, auth, layout, design system | ✅ | see below |
| 14 | `specs/14-web-overview-events.md` | overview, events explorer | ✅ | see below |
| 15 | `specs/15-web-incidents.md` | incident list/detail, timeline, graph, workflow, export | ✅ | see below |
| 16 | `specs/16-web-rules-severity.md` | rule builder, backtest, severities, allowlist | ✅ | see below |
| 17 | `specs/17-web-behavior-drift-admin.md` | behavior, drift, notifications, settings, users, audit, health | ✅ | see below |
| 18 | `specs/18-demo-e2e-deploy.md` | demo, integration + e2e tests, deployment docs | ⬜ | |
| 19 | `specs/19-final-audit.md` | audit against definition of done | ⬜ | |

## Phase 0 evidence (2026-11-17)

- **Tooling**: `pyproject.toml`, `Makefile`, `.env.example`, `.gitignore`,
  `.github/workflows/ci.yml` (Python job only; web job deferred per D-007).
- **Packages**: `core/`, `core/rules/`, `core/notifications/`, `collectors/`, `storage/`,
  `engine/`, `api/`, `api/routers/`, `tests/` each with `__init__.py`.
- **Config**: `core/config.py` + `config/settings.toml`; tests
  `tests/test_config.py` (defaults, merge, unknown keys, env overrides, relative/`~`
  paths, ranges, enums, session-key repr).
- **Time**: `core/timeutil.py`; tests `tests/test_timeutil.py` (`utc_now`, aware/naive
  conversion, injected tz, syslog format and year inference, invalid input, `parse_ts`,
  `floor_hour`, `window_bounds`).
- **Fixtures**: `tests/conftest.py` (autouse env isolation, `NOW`, `now`, `make_event`,
  `tmp_db`).
- **Docs**: `README.md`, `docs/DECISIONS.md` (D-001…D-018, tool versions), this file.
- **Commands run**: `make install`, `make test` → `24 passed`, `make lint` → ruff check
  passed, ruff format check passed, mypy `Success: no issues found in 10 source files`.
- **Commit**: `phase-0: bootstrap tooling, config, timeutil and CI skeleton`.

## Phase 1 evidence (2026-11-17)

- **Code**: `core/events.py` (taxonomy, `validate_event`, `SEVERITY_ORDER`, severity helpers),
  `core/normalizer.py` (`NormalizedEvent` TypedDict, aliases, `normalize_event`, `canonicalize`,
  `compute_event_hash`).
- **Tests**: `tests/test_events.py` (taxonomy, every required field, every type check, unknown
  keys, severity boundaries), `tests/test_normalizer.py` (worked example, every field/type alias,
  UTC conversion with patched local tz, whitespace/empty optionals, unknown-field dropping,
  hash exclusions and key-order stability, hypothesis idempotence property).
- **Commands run**: `make test` → `103 passed`; `make lint` → ruff check passed, ruff format
  check passed, mypy `Success: no issues found in 12 source files`.
- **Commit**: `phase-1: event taxonomy, validation and normalization`.

## Phase 2 evidence (2026-11-17)

- **Code**: `storage/database.py` (WAL connection pragmas, injectable path, `init_db`),
  `storage/migrations.py` (`schema_version`, `m001`, seven indexes), `storage/repositories.py`
  (events, state, audit, settings; keyset pagination; whitelisted filters).
- **Tests**: `tests/test_database.py` (pragmas, table/index creation, idempotence, legacy-DB upgrade,
  settings-derived default path), `tests/test_repositories.py` (dedup, validation, promoted
  columns, every filter, 250-event keyset pagination, time series, top values, state/audit/settings,
  concurrent writers, hypothesis round trip, static SQL scan), plus a shared `tmp_initialised_db`
  fixture in `tests/conftest.py`.
- **Commands run**: `make test` → `144 passed` (after reviewer non-blockers were fixed);
  `make lint` → ruff check passed, ruff format check passed, mypy `Success: no issues found in
  15 source files`.
- **Commit**: `phase-2: SQLite storage, migrations and repositories`.

## Phase 3 evidence (2026-11-17)

- **Code**: `collectors/__init__.py` (`CollectionResult`), `collectors/logs.py`,
  `journald.py`, `dpkg.py`, `network.py`, `listening.py`, `processes.py`, `filesystem.py`,
  `system.py`, `engine/ingest.py` (`run_collection`, `IngestReport`), `storage/migrations.py`
  (`m002`: `collector_runs`), `storage/repositories.py` (`record_collector_run`).
- **Tests**: `tests/test_collectors_logs.py` (all patterns, timestamps, incremental/rotation,
  long lines, UTF-8, permissions), `tests/test_collectors_system.py` (journald argv, both-mode
  dedup, dpkg, psutil-faked network/listening/processes, filesystem helpers, system info),
  `tests/test_ingest.py` (idempotence, state-after-save, failing collector), `tests/fuzz/test_parsers.py`
  (hypothesis fuzz of both parsers).
- **Commands run**: `make test` → `195 passed` (after reviewer non-blockers were fixed);
  `make lint` → ruff check passed, ruff format check
  passed, mypy `Success: no issues found in 24 source files`.
- **Commit**: `phase-3: read-only collectors and idempotent ingestion`.

## Phase 4 evidence (2026-11-18)

- **Code**: `core/conditions.py`, `core/severity.py`, `core/allowlist.py`, `core/enrichment.py`,
  `storage/migrations.py` (`m003`), `storage/severity_repository.py` (seeding, audited CRUD,
  `reapply_severity`), `engine/ingest.py` (real enrichment → allowlist → severity pipeline).
- **Tests**: `tests/test_conditions.py` (all ops, groups, depth, regex/CIDR safety, hypothesis),
  `tests/test_severity.py` (defaults table, override precedence, worked example),
  `tests/test_allowlist_enrichment.py` (kinds, scopes, expiry, IP scopes, no mutation),
  `tests/test_severity_storage.py` (seeding idempotence, reset, audit, reapply dry-run), plus
  updated `tests/test_database.py` and `tests/test_ingest.py`.
- **Commands run**: `make test` → `237 passed` (after reviewer non-blockers were fixed);
  `make lint` → ruff check passed, ruff format check
  passed, mypy `Success: no issues found in 29 source files`.
- **Commit**: `phase-4: condition DSL, editable severity, allowlist and enrichment`.

## Phase 5 evidence (2026-11-19)

- **Code**: `core/rules/{models,threshold,engine,backtest,defaults}.py`,
  `storage/migrations.py` (`m004`), `storage/rules_repository.py`, `engine/rules.py`,
  `engine/ingest.py` (`allowlist_suppressed` enrichment flag).
- **Tests**: `tests/test_rules_models.py` (validation paths/warnings), `tests/test_rules_threshold.py`
  (boundaries, sliding/fixed, escalation, `test_user_example_tiers`, hypothesis order invariance),
  `tests/test_rules_storage.py` (versions, reset, soft delete, unique findings),
  `tests/test_rules_backtest_engine.py` (backtest limits/noise, deterministic `rule_triggered`,
  200k-event performance budget), updated `tests/test_database.py`.
- **Commands run**: `make test` → `290 passed` (after reviewer blockers were fixed);
  `make lint` → ruff check passed, ruff format check
  passed, mypy `Success: no issues found in 36 source files`.
- **Performance**: 200 000 events evaluated in **0.751 s** (budget 30 s; recorded in D-051).
- **Commit**: `phase-5: rule models, threshold evaluator, persistence and backtest`.

## Phase 6 evidence (2026-11-19)

- **Code**: `core/rules/{models,sequence,new_value,field_match,engine,defaults}.py`,
  `engine/rules.py` (history injection), `docs/RULES.md` (every kind and seeded rule).
- **Tests**: `tests/test_rules_advanced.py` (sequence, new-value, field-match, reserved kinds,
  property tests), `tests/test_rules_seeded.py` (16 rules, seeding/reset/disabled default,
  cross-kind worked example), updated `tests/test_rules_backtest_engine.py`.
- **Commands run**: `make test` → `307 passed` (after reviewer blockers were fixed);
  `make lint` → ruff check passed, ruff format check
  passed, mypy `Success: no issues found in 39 source files`.
- **Commit**: `phase-6: sequence, new-value, field-match and seeded rules`.

## Phase 7 evidence (2026-11-19)

- **Code**: `core/{correlation,incidents,timeline,mitre}.py`, `storage/migrations.py` (`m005`),
  `storage/incident_repository.py`, `engine/correlation.py`.
- **Tests**: `tests/test_correlation.py` (all link kinds, strengths, anchors, root/ignore, span
  split, allowlist, shuffle determinism), `tests/test_incidents.py` (plan actions, title/summary,
  timeline/caveats, status matrix, MITRE, storage round trips, `test_incident_worked_example`),
  updated `tests/test_database.py`.
- **Commands run**: `make test` → `327 passed` (after reviewer blockers were fixed);
  `make lint` → ruff check passed, ruff format check
  passed, mypy `Success: no issues found in 45 source files`.
- **Commit**: `phase-7: correlation, incidents, timeline, workflow and MITRE`.

## Phase 8 evidence (2026-11-19)

- **Code**: `core/{baseline,anomaly_detection}.py`, five seeded `baseline_metric` rules in
  `core/rules/defaults.py`, `storage/migrations.py` (`m006`), `storage/baseline_repository.py`,
  `engine/baselines.py`, `docs/RULES.md` baseline section.
- **Tests**: `tests/test_baseline.py` (zero-fill, exact stats, exclusions, maturity, hour-of-week,
  hypothesis), `tests/test_anomaly_detection.py` (worked example, floors, tiers, dedup),
  `tests/test_baseline_engine.py` (seeding, idempotent anomaly cycle, series), updated
  `tests/test_rules_seeded.py` and `tests/test_database.py`.
- **Commands run**: `make test` → `347 passed` (after reviewer blockers were fixed);
  `make lint` → ruff check passed, ruff format check
  passed, mypy `Success: no issues found in 49 source files`.
- **Commit**: `phase-8: behavioral baselines and explained anomalies`.

## Phase 9 evidence (2026-11-19)

- **Code**: `core/drift_detection.py`, `collectors/filesystem.py` (`take_snapshot`),
  `storage/migrations.py` (`m007`), `storage/drift_repository.py`, `engine/drift.py`,
  `engine/ingest.py` (`prepare_event`), `docs/LIMITATIONS.md`.
- **Tests**: `tests/test_drift_detection.py` (comparison, flags, metadata-only enforcement,
  validation, hypothesis), `tests/test_drift_engine.py` (init/check/reported-once, approval audit,
  worked example), updated `tests/test_database.py`.
- **Commands run**: `make test` → `370 passed` (after reviewer gaps were addressed);
  `make lint` → ruff check passed, ruff format check
  passed, mypy `Success: no issues found in 52 source files`.
- **Commit**: `phase-9: read-only config drift and persistence monitoring`.

## Phase 10 evidence (2026-11-19)

- **Code**: `core/risk_scoring.py`, four seeded `incident_meta` rules, `m008`
  (`risk_assessments`, `risk_changes`), `storage/risk_repository.py`, `engine/scoring.py`,
  `docs/RISK_RULES.md`, updated `docs/RULES.md`.
- **Tests**: `tests/test_risk_scoring.py` (boundaries, distinct rules, cap/floor, meta metrics,
  decay, hypothesis reason-sum, `test_risk_worked_example`), `tests/test_risk_storage.py`
  (upsert, propagation, severity-change once, generated docs), updated seeded/database tests.
- **Commands run**: `make test` → `399 passed` (after reviewer blockers were fixed);
  `make lint` → ruff check passed, ruff format check
  passed, mypy `Success: no issues found in 55 source files`.
- **Commit**: `phase-10: explainable risk scoring and incident-meta rules`.

## Phase 11 evidence (2026-11-19)

- **Code**: `core/{pipeline,retention,export,health}.py`, `core/notifications/*`,
  `engine/{runner,scheduler,notifier,logging_setup}.py`, `cli.py`, `m009`,
  `storage/{notification_repository,retention_repository}.py`, `docs/OPERATIONS.md`, Makefile.
- **Tests**: `tests/test_scheduler.py`, `test_retention.py`, `test_notifications.py`, `test_export.py`,
  `test_pipeline_cli.py`, `test_health_logging.py`, updated `tests/test_database.py`.
- **Commands run**: `make test` → `425 passed` (after reviewer and security-auditor fixes);
  `make lint` → ruff check passed, ruff format check
  passed, mypy `Success: no issues found in 68 source files`.
- **Commit**: `phase-11: pipeline, engine daemon, CLI, retention and notifications`.

## Phase 12 evidence (2026-11-19)

- **Code**: `core/auth.py`, `api/{main,deps,security,schemas}.py`, `api/routers/*.py`,
  `storage/{migrations,auth_repository}.py` (`m010`), `core/config.py`, `cli.py`,
  `web/openapi.json`, `docs/API.md`, `make openapi`.
- **Tests**: `tests/test_auth.py`, `tests/api/test_auth_flow.py`, `tests/api/test_endpoints.py`,
  updated CLI/database/conftest fixtures.
- **Commands run**: `make test` → `505 passed` (after reviewer and security-auditor fixes);
  `make lint` → ruff check passed, ruff format check
  passed, mypy `Success: no issues found in 81 source files`.
- **Commit**: `phase-12: FastAPI auth, RBAC, REST, SSE and OpenAPI`.
- **Follow-up**: added `httpx2` 2.16.2 to dev dependencies (D-086) to remove the Starlette
  `TestClient` deprecation warning; suite remains green with no warnings.

## Phase 13 evidence (2026-11-19)

- **Code**: `web/` App Router scaffold, typed client (`lib/api/{client,hooks}.ts`,
  generated `schema.d.ts`), auth/RBAC helpers, SSE hook with polling fallback,
  design-system components, layout/shell, every page from spec 13.3, `middleware.ts`,
  `next.config.ts`, Makefile `web`/`web-test`/`web-e2e`, `.github/workflows/ci.yml`,
  plus `GET /api/changes` in `api/routers/stream.py` as the documented SSE fallback.
- **Tests**: Vitest unit/component tests under `web/tests/` (8 files, 29 tests),
  `web/e2e/smoke.spec.ts` with `web/playwright.config.ts`, and
  `tests/api/test_endpoints.py::test_changes_polling_fallback`.
- **Commands run**: `make test` → `506 passed`; `make lint` → ruff/format/mypy clean;
  `npm test` → `29 passed`; `npm run typecheck`, `npm run lint`, `npm run build` → pass.
  `make web` served on `127.0.0.1:3000`; verified `/login` security headers and the
  `/events` → `/login?next=%2Fevents` redirect.
- **Commit**: `phase-13: Next.js foundation, typed client, auth and design system`.

## Phase 14 evidence (2026-11-19)

- **Code**: `web/components/overview/*`, `web/components/events/*`, `web/lib/{filters,events}.ts`,
  expanded `web/lib/api/hooks.ts`/`query-keys.ts`; `api/routers/events.py` (CIDR filter,
  severity-grouped stats, filter-aware bounded export) and `storage/{database,repositories}.py`.
- **Tests**: `web/tests/{lib,components,integration}/*` (13 files, 61 tests),
  `web/e2e/overview-events.spec.ts`, `tests/test_event_explorer_api.py`,
  `tests/test_seed_demo_db.py`, added API tests for stats and export.
- **Commands run**: `make test` → `514 passed`; `make lint` → ruff/format/mypy clean;
  `npm test` → `61 passed`; `npm run typecheck`, `npm run lint`, `npm run build` → pass;
  `npx playwright test --list` → `6 tests in 2 files`.
- **Commit**: `phase-14: Overview and Events explorer with typed filters and exports`.

## Phase 15 evidence (2026-11-19)

- **Code**: `api/routers/incidents.py` (cursor list, history, bulk status, graph entities,
  proper export responses), `api/schemas.py`, `storage/incident_repository.py`
  (`list_incidents_page`), `scripts/seed_demo_db.py` (standard scenario incident),
  `web/lib/incident/*`, `web/components/incidents/*`, both incident pages.
- **Tests**: `web/tests/lib/incident/helpers.test.ts`, `web/tests/components/{incidents,incident-list}.test.tsx`,
  `web/e2e/incidents.spec.ts`, `tests/api/test_incidents_extended.py`,
  `tests/test_incident_list_page.py`, updated seed test.
- **Commands run**: `make test` → `531 passed`; `make lint` → ruff/format/mypy clean;
  `npm test` → `87 passed`; `npm run typecheck`, `npm run lint`, `npm run build` → pass.
- **Commit**: `phase-15: Incident investigation UI, workflow and explanations`.

## Phase 16 evidence (2026-11-19)

- **Code**: `api/routers/rules.py` (catalogue, all-rule export, path-aware import, version restore),
  `storage/rules_repository.py`, `web/lib/rules/helpers.ts`, `web/components/{rules,conditions,severity,allowlist}/**`,
  the rules/severity/allowlist pages, `docs/RULES.md`.
- **Tests**: `web/tests/lib/rules/helpers.test.ts`, `web/tests/components/rules.test.tsx`,
  `web/e2e/rules.spec.ts`, `tests/api/test_rules_ui_api.py`.
- **Commands run**: `make test` → `541 passed`; `make lint` → ruff/format/mypy clean;
  `npm test` → `110 passed`; `npm run typecheck`, `npm run lint`, `npm run build` → pass.
- **Commit**: `phase-16: Rule builder, backtest, severity and allowlist UI`.

## Phase 17 evidence (2026-11-19)

- **Code**: enriched `api/routers/system.py` (`/system/info`, filters/cursors on `/audit`, users
  guard rails, session revocation), `api/routers/config_router.py` (env-name validation for channel
  secrets), `storage/repositories.py` (audit cursors), `web/lib/admin/helpers.ts`,
  `web/components/{behavior,drift,notifications,settings,users,audit,health}/**`, all seven pages.
- **Tests**: `web/tests/lib/admin/helpers.test.ts`, `web/tests/components/admin.test.tsx`,
  `web/e2e/admin.spec.ts`, `tests/api/test_admin_ui_api.py`.
- **Commands run**: `make test` → `551 passed`; `make lint` → ruff/format/mypy clean;
  `npm test` → `125 passed`; `npm run typecheck`, `npm run lint`, `npm run build` → pass.
- **Commit**: `phase-17: Behavior, drift and administration UI`.
