# Phase 19 — final audit report

Date: 2026-11-21. Scope: the whole repository, plus the four extra audit items
requested for this phase. All commands were run from the project root with
`./venv/bin/python`, `npm`/`npx` from the pinned Node installation, and **no
`sudo`**.

## 1. Requirement matrix and test evidence

| Requirement (master prompt section) | Evidence |
|---|---|
| Event format, validation, normalizer aliases (4.1) | `core/events.py`, `core/normalizer.py`; `tests/test_events.py::test_invalid_severity`, `tests/test_normalizer.py` |
| UTC timestamps, injected `now` (4.2) | `core/timeutil.py::window_bounds`, `tests/test_timeutil.py::test_window_bounds_returns_start_and_end` |
| Config split static/DB (4.3) | `core/config.py`, `docs/DECISIONS.md`; `tests/test_config.py::test_session_key_value_never_in_repr` |
| SQLite schema + migrations, parameterised SQL (4.4) | `storage/database.py`, `storage/migrations.py`; `tests/test_security_scans.py::test_storage_sql_is_parameterised`, `tests/test_database.py` |
| Rules: tiers/windows/cooldown (4.5) | `core/rules/threshold.py`; `tests/test_rules_threshold.py::test_user_example_tiers`, `::test_window_edge_is_exclusive`, `tests/test_time_windows_audit.py::test_sliding_window_edges` |
| Severity resolution order (4.6) | `core/severity.py`, `engine/ingest.py`; `tests/test_allowlist_enrichment.py`, `tests/test_ingest.py::test_collected_events_carry_resolved_severity_and_enrichment` |
| Auth/session/CSRF/RBAC/headers (4.7) | `api/main.py`, `api/security.py`; `tests/api/test_auth_flow.py`, `tests/api/test_security_matrix.py`, `tests/test_api_security_startup.py`, `web/tests/csp-production.test.ts` |
| Incident reconstruction + caveats (mission 1) | `core/correlation.py`, `core/timeline.py`; `tests/test_correlation.py`, `tests/test_incidents.py`, `tests/test_demo_spec_gaps.py::test_demo_incident_explanation_api_has_strong_and_weak_reasons` |
| Baselines + explained anomalies (mission 2) | `core/baseline.py`, `core/anomaly_detection.py`; `tests/test_baseline.py`, `tests/test_anomaly_detection.py`, `tests/test_time_windows_audit.py` |
| Drift monitoring, fingerprints (mission 3) | `collectors/filesystem.py`, `core/drift_detection.py`; `tests/test_drift_detection.py`, `tests/test_demo_spec_gaps.py::test_demo_authorized_keys_drift_names_key_fingerprints` |
| Explainable scoring (mission 4) | `core/risk_scoring.py`; `tests/test_risk_scoring.py::test_score_severity_boundaries`, `::test_rule_floor_decides_severity` |
| User control (spec task 4) | see §2 |
| Idempotence / order independence | `tests/integration/test_full_scenario.py::test_shuffled_event_order_is_equivalent`, `tests/test_rules_threshold.py::test_findings_invariant_under_input_order`, `tests/test_engine_lookback.py` |
| Tooling / CI (4.8) | `Makefile`, `pyproject.toml`, `.github/workflows/ci.yml`; `make test`, `make lint`, `make web-test`, `make web-e2e` all run locally with the summary lines in §10 |
| Every finding shows rule, tier, evidence; every incident shows timeline, reasons and score reasons (DoD 7) | `core/timeline.py`, `core/risk_scoring.py`; `tests/test_incidents.py`, `tests/test_risk_scoring.py`, `tests/test_demo_spec_gaps.py::test_demo_incident_explanation_api_has_strong_and_weak_reasons`, `web/e2e/incidents.spec.ts` |
| No remediation, no writes outside project/monitored paths (DoD 7) | read-only collectors; `tests/test_security_scans.py`, `tests/test_phase19_security.py`, `docs/DECISIONS.md` D-108/D-110 |
| Docs match code; `PROGRESS.md` fully checked; demo reproducible (DoD 7) | `PROGRESS.md` phase table row 19 ✅ with evidence below; `docs/DECISIONS.md`; `tests/test_docs_coverage.py`, `tests/test_demo.py`, `web/e2e/demo-seed.ts` |

All 19 phase deliverables are present; deviations are recorded in
`docs/DECISIONS.md` (D-001 … D-109). No Phase 20 work was started.

## 2. User-control verification

| Control | Test(s) |
|---|---|
| Custom threshold rule, ≥2 tiers and windows | `tests/test_rules_threshold.py::test_user_example_tiers` (5/20/50 example), `tests/test_rules_models.py` |
| Edit default severity | `tests/test_severity_storage.py::test_default_edit_reset_and_audit`, `tests/integration/test_rule_edit_flows.py::test_default_severity_change_and_reapply` |
| Conditional severity override | `tests/test_severity_storage.py::test_override_crud_and_ordering`, `tests/test_allowlist_enrichment.py::test_each_kind_matches` |
| Allowlist with reason/expiry | `tests/test_severity_storage.py::test_allowlist_crud`, `tests/test_allowlist_enrichment.py::test_expiry_and_disabled` |
| Reset rules/severities/overrides | `tests/test_rules_seeded.py::test_seeding_idempotent_reset_and_disabled_default`, `tests/test_severity_storage.py::test_default_edit_reset_and_audit` |
| Backtest | `tests/test_rules_backtest_engine.py::test_backtest_counts_noise_and_no_persistence`, `::test_backtest_range_and_should_stop` |
| Versions / restore | `tests/test_rules_storage.py::test_version_bump_and_audit`, `tests/api/test_rules_ui_api.py::test_restore_version_creates_new_version` |
| Audit entries | `tests/integration/test_rule_edit_flows.py::test_config_mutations_are_audited`, `tests/test_repositories.py::test_audit_write_and_list`, `tests/api/test_admin_ui_api.py::test_audit_filters` |

## 3. Extra audit item 1 — time-window boundaries and properties

`tests/test_time_windows_audit.py` (8 tests) covers:

- `hourly_buckets`: events at `:00:00`, `:30:00` and `:59:59.999999` of the
  evaluated hour, across midnight, the current partial hour excluded,
  baseline/rule/allowlisted exclusions, 168 zero-filled buckets, and a
  Hypothesis property that bucket count is always `window_days * 24` and the
  bucket sum equals the number of in-window events.
- Re-audit of other windows: threshold sliding `(start, end]` (start-exclusive,
  end-inclusive), fixed minute/hour alignment with matching
  `window_seconds`, correlation `window_minutes` inclusive end and exclusive
  `+1 s`, retention `timestamp < cutoff` strict, drift (no time window — only
  snapshot comparison, `engine/drift.py::check_drift`).
- Regression proof: reverting the `hourly_buckets` fix makes
  `test_hourly_buckets_counts_all_instant_boundaries` fail (`1 == 3`); the
  test therefore catches the original bug.

## 4. Extra audit item 2 — engine lookback vs baseline cycle

`engine/rules.py::event_lookback_seconds()` is a pure, tested helper. It
returns the maximum over enabled rules of
`max(tier windows, step windows, sequence within_seconds) + cooldown` (minimum
60 s) and is the value actually passed to `get_events_for_rules()` in `run_rules`.
Tests: `tests/test_engine_lookback.py::test_lookback_covers_every_enabled_rule_window_plus_cooldown`,
`::test_lookback_covers_sequence_within_seconds`, `::test_enabled_rule_set_lookback_matches_helper`.

`tests/test_engine_lookback.py::test_analyze_cycle_with_60s_interval_keeps_evaluating_last_completed_hour`
runs a real engine cycle with collectors disabled and a 12-event spike in the
last completed hour, then repeats at `+60 s`: the anomaly is produced once and
is not duplicated. Baselines query seven days of history directly
(`engine/baselines.py::run_baselines`), so they are not limited by the rules
lookback. **No mismatch found; the helper was extracted to make the invariant
explicit and testable.**

## 5. Extra audit item 3 — real smoke test (non-privileged, no sudo)

Run as user `mouad` (groups include `adm`, no `sudo`) with the project-local DB
`sentinel.db` (git-ignored):

```
$ ./venv/bin/python cli.py init
initialised sentinel.db
$ ./venv/bin/python cli.py collect
events_new=113
$ ./venv/bin/python cli.py collect --json
{"events_found": 23, "events_new": 11, "runs": [{"collector": "auth_log", ...}], "warnings": []}
$ ./venv/bin/python cli.py analyze
analysis complete
```

Warnings: **none**. The `auth_log`, `dpkg`, `network`, `listening`, `processes`
and `system` collectors all reported `status: "ok"`; the user is in group
`adm`, so `/var/log/auth.log` was readable without permission warnings. No
monitored path was written to.

Live-machine state after the run (from `sentinel.db`): 124 events total —
78 `sudo_command` (auth_log), 34 `network_connection`, 8 `package_installed`,
3 `process_started`, 1 `system_info`; all severity `low`; 44 events within the
last 24 h. There are **no failed logins**, so no rule findings, incidents or
risk assessments; baselines are immature (history far shorter than 24 h) and
no anomaly was emitted. `cli.py analyze` does not run the drift cycle, so the
drift page would have no snapshots until `cli.py drift init/check` or a full
`cli.py engine --once`. The dashboard would therefore show non-zero "Events
(24 h)", zero "Failed logins", "No open incidents", and empty behavior/drift
views — correct for this quiet host. This is a real-machine observation, not a
simulated assertion.

## 6. Extra audit item 4 — hand-written test data and fixture replacement

Generated fixtures already in use: `tests/test_api_fixtures.py` writes 20 API
responses to `web/tests/fixtures/*.json` with a staleness test; Vitest/MSW tests
consume them. New in this phase: `tests/fixtures/real_events.py` generates
events through the **real** `parse_auth_line()` + `prepare_event()` pipeline.
`tests/test_event_explorer_api.py` previously hand-wrote three `auth.log`
events with the wrong source name (`auth.log`); it now uses the generated
events (only severity is pinned for the mixed-series assertion).

Remaining hand-written data, with the reason it stays hand-written:

| Location | Why it is retained |
|---|---|
| `tests/conftest.py::make_event` | minimal canonical event builder; shape itself is tested by `tests/test_events.py` |
| `tests/test_normalizer.py`, `tests/fuzz/*` | deliberately malformed/alias inputs to exercise validation; generated collector output would hide those cases |
| `tests/test_collectors_logs.py`, `tests/test_collectors_system.py` | already feed synthetic raw lines / fake psutil objects into the real parsers |
| `tests/test_rules_threshold.py`, `tests/test_correlation.py`, `tests/test_risk_scoring.py`, `tests/test_baseline.py` | crafted boundary values (N−1/N/N+1, exact seconds) that generated data cannot express deterministically |
| `tests/api/*`, `tests/test_repositories.py`, `tests/test_export.py`, `tests/test_event_explorer_api.py`, `tests/integration/*`, `tests/test_api_fixtures.py` | request bodies or DB seeds with explicit expectations; API *response* drift is already covered by the generated `web/tests/fixtures` |
| `tests/test_api_security_startup.py`, `tests/test_demo_spec_gaps.py` | config values, not collector/API payloads |

Conclusion: payload-shape drift is now covered in both directions — real API →
web fixtures, real collector → Python event fixtures. Crafted boundary inputs
remain intentionally hand-written.

## 7. Security verification

- Static scans: `tests/test_security_scans.py::test_no_dangerous_calls_or_shell`,
  `::test_storage_sql_is_parameterised`, `::test_no_secret_or_cmdline_storage`,
  `::test_gitignore_ignores_secrets_and_demo`.
- Runtime: `tests/test_phase19_security.py::test_default_config_makes_no_outbound_connections`
  fails on any `socket.create_connection` / `smtplib.SMTP` call;
  `::test_demo_db_stores_no_secrets_contents_or_command_lines` scans stored
  `event_data` for key material, passwords, command lines and shadow paths.
- Forwarded-header trust invariant: `docs/DECISIONS.md` D-108/D-109 and
  `tests/test_api_security_startup.py` (loopback bind, refusal without
  `allow_remote` + `trusted_proxy`, warning with them, no secret in logs).
- Dependency audit: `npm audit --omit=dev` → `found 0 vulnerabilities`;
  `pip-audit` is **not installed** (not installed per instruction).
  Dependency versions are recorded in the environment table at the top of `docs/DECISIONS.md` and in D-014/D-107.
- Headers/CSP/cookies/CSRF/RBAC: `tests/api/test_security_matrix.py`,
  `tests/api/test_auth_flow.py`, `web/tests/csp-production.test.ts`,
  `web/e2e/login-production.spec.ts`. CSRF is parameterised over every unsafe
  route in the freshness-checked OpenAPI snapshot; RBAC uses an explicit admin
  route list plus per-route `Depends(admin_user)` in the routers (a newly added
  admin-only route is not auto-discovered by that test — open risk in §9).

## 8. Performance notes (measured, with honest limits)

- Rule evaluation over 200 000 events: `tests/test_rules_backtest_engine.py::test_performance_budget`
  asserts `< 30 s` (passing).
- Baseline computation over 30 days × 50 subjects:
  `tests/test_baseline.py::test_performance_30_days_50_subjects` asserts `< 10 s` (passing).
- 10 000-event ingestion burst: `tests/integration/test_pipeline_failure_modes.py`
  asserts `< 60 s` (passing).
- `scripts/benchmark.py` was run 5 times on the current commit (`43ce0d7`) and 5 times in a worktree
  on the last pre-correlation-fix commit (`a21b707`), interleaved in alternating order on
  2026-11-22. No project tests, servers, builds or browsers were running; persistent desktop
  services n8n (PIDs 3087, 3303) and chrome_crashpad handlers were present. Load average before
  each run: current 1.81, 2.23, 2.17, 3.18, 3.08; pre-fix 2.13, 2.17, 2.28, 2.53, 2.92.
  Machine: Linux-7.0.0-42-generic-x86_64-with-glibc2.39, x86_64 with 8 logical CPUs,
  16,479,649,792 bytes RAM, Python 3.12.3 CPython.
- Medians (current | pre-fix): ingestion **13474.7 | 13575.4 events/s** (ranges 9415.7–29138.3 and
  10555.6–20842.5); rule evaluation over 200k events **2.067 | 2.186 s** (1.032–2.742 and
  1.464–2.777); `/api/events` median **26.45 | 32.42 ms** (10.54–38.95 and 10.49–45.84), p95
  **30.92 | 50.88 ms**; `/api/incidents` median **18.7 | 22.91 ms** (7.99–20.36 and 8.46–39.52),
  p95 **22.48 | 27.73 ms**; DB size per 100k events **73,129,984 bytes in all 10 runs**.
- Every between-commit median difference is smaller than the run-to-run spread within each
  variant, so **no regression or improvement can be claimed** from these measurements. Full
  per-run data is in `metrics.json` → `performance.benchmark_detail` and `docs/METRICS.md`.

## 9. Known limitations / open risks

- Heuristic thresholds are uncalibrated; an anomaly is unusual, not necessarily
  malicious. MITRE mapping is indicative only.
- Polling collectors can miss short-lived connections and change-and-revert
  drift; `psutil` snapshot details may need privileges.
- Drift detection is snapshot-based (no inotify). Multi-host agents, GeoIP/DNS
  lookups and ML-assisted baselines are explicitly out of scope.
- The demo DB is shared by all Playwright workers, hence `workers: 1` and a
  fresh demo seed for a clean run.
- Non-loopback API exposure with `trusted_proxy` requires the operator to strip
  client-supplied `X-Forwarded-*` at the proxy edge (warning at startup).
- Playwright reuses existing servers (`reuseExistingServer: !CI`); a stale
  `next-server`/`uvicorn` holding port 3000/8000 makes a run hang until the
  webServer timeout. Stop old dev servers before `make web-e2e`.

## 10. Test and lint summary lines (paste from the actual runs)

```
make test        -> 608 passed in 179.32s (0:02:59) [final run]
make coverage    -> TOTAL 6113 715 88% ; 608 passed in 201.25s
make lint        -> ruff check: All checks passed! / ruff format: 154 files already formatted /
                    mypy: Success: no issues found in 82 source files
make web-test    -> next build: Finished TypeScript / Compiled successfully;
                    vitest: Test Files 28 passed (28), Tests 137 passed (137);
                    tsc --noEmit: clean; eslint: clean
make web-e2e     -> 22 passed (1.4m) against npm run start (production build)
npm audit --omit=dev -> found 0 vulnerabilities
pip-audit        -> not installed (not installed without asking)
```

## 11. Phase 19 reviewer and security-auditor outcome

`/review 19`: no blockers. Majors found and fixed before reporting — (a) two
engine tests still read the real `/var/log/auth.log`; their settings now point
`paths.auth_log` at an empty tmp file, so the phase's isolation claim is true;
(b) `PROGRESS.md` still marked phase 19 "not started" and contained stale
"No Phase 19 work started" lines; the phase table row is now ✅ with evidence.
The requirement matrix now covers master-prompt §4.8 and the §7 DoD bullets,
and the "commit pending" line is accurate until the commit is made.

`security-auditor`: no production security regression; the smoke test is safe.
High finding fixed — the "no outbound connections" test previously disabled
the notifier and used hardened settings; it now uses the real defaults with
`notify=True`, patches `create_connection`/`getaddrinfo`/`gethostbyname`/
`smtplib.SMTP`/`httpx.post`, and the report wording is corrected. Medium
findings fixed — the demo-DB secret scan now uses the *actual* planted password
and session key, paginates all events, and checks the generic `ssh-ed25519 `
prefix; the RBAC claim in §7 is softened to match the real coverage. Remaining
non-blockers: RBAC's hand-maintained admin-route list (§9), no measured
ingestion/API-latency/DB-size numbers (§8), and `pip-audit` unavailable.

## 12. Suggested future work

inotify-based drift, multi-host agents, calibrated thresholds, Docker
packaging, i18n, and a proper benchmark harness for the unmeasured numbers in §8.
