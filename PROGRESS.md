# Progress

Phases are completed one at a time. "Evidence" names the files and test names that
satisfy each gate. Status legend: ✅ done · ⬜ not started.

| # | Spec | Deliverable | Status | Evidence |
|---|---|---|---|---|
| 0 | `specs/00-bootstrap.md` | repo, tooling, config, timeutil, CI skeleton | ✅ | see below |
| 1 | `specs/01-events-normalizer.md` | validation, normalizer, event taxonomy | ⬜ | |
| 2 | `specs/02-storage.md` | SQLite schema v1, migrations, repositories, audit log | ⬜ | |
| 3 | `specs/03-collectors-ingestion.md` | all collectors, ingestion, fuzz tests | ⬜ | |
| 4 | `specs/04-severity-allowlist-enrichment.md` | editable defaults/overrides, allowlist, enrichment | ⬜ | |
| 5 | `specs/05-rules-engine-core.md` | rule models, conditions, threshold evaluator, backtest | ⬜ | |
| 6 | `specs/06-rules-engine-advanced.md` | sequence, new-value, field-match, seeded default rules | ⬜ | |
| 7 | `specs/07-correlation-incidents.md` | correlation, incidents, timeline, workflow, MITRE | ⬜ | |
| 8 | `specs/08-baselines-anomalies.md` | baselines, baseline-metric rules, anomalies | ⬜ | |
| 9 | `specs/09-config-drift.md` | files, dirs, persistence, authorized_keys | ⬜ | |
| 10 | `specs/10-risk-scoring.md` | incident-meta rules, scoring, recency decay | ⬜ | |
| 11 | `specs/11-pipeline-engine-ops.md` | pipeline, engine loop, CLI, retention, notifications, exports, logging | ⬜ | |
| 12 | `specs/12-api.md` | FastAPI, auth, RBAC, CSRF, SSE, OpenAPI | ⬜ | |
| 13 | `specs/13-web-foundation.md` | Next.js scaffold, API client, auth, layout, design system | ⬜ | |
| 14 | `specs/14-web-overview-events.md` | overview, events explorer | ⬜ | |
| 15 | `specs/15-web-incidents.md` | incident list/detail, timeline, graph, workflow, export | ⬜ | |
| 16 | `specs/16-web-rules-severity.md` | rule builder, backtest, severities, allowlist | ⬜ | |
| 17 | `specs/17-web-behavior-drift-admin.md` | behavior, drift, notifications, settings, users, audit, health | ⬜ | |
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
