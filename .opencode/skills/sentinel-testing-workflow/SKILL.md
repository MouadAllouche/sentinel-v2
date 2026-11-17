---
name: sentinel-testing-workflow
description: Test-first workflow, isolation rules, fixtures, property/fuzz/e2e testing patterns and the per-phase definition of done for Sentinel. Load at the start of every phase and whenever writing, fixing or reviewing tests.
---

# Testing workflow

## Loop
Write tests → see them fail for the right reason → implement → pass → run the **whole** suite (`make test`, plus `make web-test` once web exists) → `make lint` → `/review N`. Never weaken or delete a test to get green; if the spec is wrong, say so and propose a fix.

## Isolation (mandatory)
No test touches the real DB, `/var/log`, `/etc`, the real network, SMTP, webhooks or the real clock. `tests/conftest.py` autouse fixture sets `SENTINEL_DB_PATH`/`SENTINEL_CONFIG` to tmp. Use `tmp_path`, `monkeypatch`, fixed `NOW`, injectable `now`, fake transports, `SimpleNamespace` psutil objects (`monkeypatch.setattr("collectors.network.psutil.net_connections", lambda kind: [...])`). A test may assert that default config creates no sockets.

## Kinds
- Unit (pure `core/`), integration (pipeline on tmp DB), API (`TestClient`), fuzz/property (hypothesis: parsers never raise and emit valid events; evaluators never raise; **order independence** and **idempotence** of rules/correlation/scoring), web unit (Vitest + Testing Library + MSW), e2e (Playwright vs seeded demo DB).
- Always cover: happy path, **boundaries** (N−1/N/N+1; 19/20, 39/40, 69/70; window edges), empty/malformed input, permission/unavailable data, duplicates, idempotence, RBAC (parametrised over every mutating route), audit rows for every mutation.
- Named scenario tests: `test_user_example_tiers`, `test_incident_worked_example`, `test_risk_worked_example`, `test_full_scenario`.

## Fixtures
`NOW`, `make_event(**overrides)`, `tmp_db` (initialised + seeded), `auth_log_file` builder, `scenario_events()` (failed logins → success → sudo → drift), `api_client(role)`, `seeded_demo_db` (shared with Playwright via `scripts/seed_demo_db.py`).

## Definition of done (per phase)
All new + existing tests green (paste summary lines) · lint/mypy clean · reviewer subagent blockers fixed · `PROGRESS.md` and `docs/DECISIONS.md` updated · commit `phase-N: summary` · report: Done / Tests / Reviewer findings / Decisions / Risks / Next. Then stop.
