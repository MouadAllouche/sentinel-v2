# Decisions and deviations

Authoritative order: `AGENTS.md` → `SENTINEL_MASTER_PROMPT.md` → `specs/NN-*.md`.
Where the specs are ambiguous or conflict, the decision below is recorded before
implementation. Entries are dated; "alternatives" records what was rejected.

## Toolchain observed at bootstrap (2026-11-17)

| Tool | Detected / chosen | Notes |
|---|---|---|
| Python | 3.12.3 (system and `venv/bin/python`) | `venv` already present; `pip` 24.0 |
| Node | v24.22.1 | via nvm at `/home/mouad/.nvm/versions/node/v24.22.1/bin/node` |
| npm | 11.19.1 | same nvm installation |
| Next.js | *not installed; to be pinned in Phase 13* | no `web/` or `package-lock.json` yet; exact version recorded here when scaffolded |

Python packages installed in `./venv` on 2026-11-17 (`pip install -e ".[dev]"`):
`fastapi 0.163.1`, `uvicorn 0.54.0`, `pydantic 2.14.3`, `psutil 7.2.2`,
`httpx 0.28.1`, `reportlab 5.1.0`, `pytest 9.2.0`, `pytest-cov 7.1.0`,
`hypothesis 6.170.15`, `ruff 0.17.5`, `mypy 2.4.1`, `types-psutil 7.2.2.20261111`,
`coverage 7.17.3`, `starlette 1.10.0`.

---

## User decisions (given at the start of Phase 0)

### D-001 — Event-type `enabled=false` drops evidence (C1, Phase 4)
- **Decision**: implement spec 04 §4.2 as written — disabling an event type skips storing it; the
  evidence-loss warning must be prominent in the UI and in docs.
- **Reason**: user explicitly chose literal spec behavior over the "never drop evidence" ideal.
- **Alternatives**: store but mark disabled (rejected — contradicts the spec's storage semantics).

### D-002 — Incident creation gate (C2, Phase 7)
- **Decision**: use the stricter rule from the spec 07 worked example: an incident is created only
  when the component contains a finding with `actions.create_incident=true` **or** an anchor of
  severity ≥ medium. Anchors still define components and weak links can extend them.
- **Reason**: avoids low-value incidents from lone low-severity events.
- **Alternatives**: create an incident for any component with an anchor (rejected).

### D-003 — `severity_source` labels (C3, Phase 4 and later)
- **Decision**: treat `"fallback"` as `"default"` wherever storage or validation encounters it;
  events whose severity was lowered by the allowlist use `"allowlist:<id>"`.
- **Reason**: resolves the enum mismatch between master 4.1/spec 01 and spec 04 without breaking
  existing consumers.
- **Alternatives**: add a third enum value (rejected — would fragment the taxonomy).

### D-004 — Migration for API tables (G1, Phase 12)
- **Decision**: add migration `m010` in Phase 12 creating `users`, `sessions` and `saved_filters`.
- **Reason**: master 4.4 assigns these tables to Phase 12 but spec 12 omits the migration; every
  phase appends exactly one ordered migration.
- **Alternatives**: fold them into `m009` (rejected — breaks the one-migration-per-phase rule).

### D-005 — Health module (G2, Phase 11)
- **Decision**: add `core/health.py` with `get_health(db_path)` in Phase 11.
- **Reason**: spec 11.7 requires it; the master file tree omits it.

### D-006 — Session key availability (G3, Phase 12 and 18)
- **Decision**: the API refuses to start when `SENTINEL_SESSION_KEY` is absent. Tests inject a fixed
  key via fixtures. The demo may generate a key file **inside `demo_workdir/` only**.
- **Reason**: fail closed, keep secrets out of the repository, keep tests hermetic.
- **Alternatives**: auto-generate an ephemeral key at startup (rejected — sessions would invalidate
  on restart and it weakens the fail-closed guarantee).

### D-007 — Web CI job (G4, Phase 0)
- **Decision**: no commented-out stub in `.github/workflows/ci.yml`; this DECISIONS entry is the
  only notice that the web job lands in Phase 13.
- **Reason**: AGENTS.md forbids stubs; a note is accurate documentation, not dead code.

### D-008 — Journald/auth dedup test (R1, Phase 3)
- **Decision**: keep a pinned test asserting `auth_source="both"` produces no duplicate events
  from journald and auth.log.
- **Reason**: timestamps must normalise identically for the event hash to deduplicate.

### D-009 — Backtest deadline (R2, Phase 5 and 12)
- **Decision**: `backtest_rule` accepts a `should_stop: Callable[[], bool]` supplied by the API
  layer, checked between groups. `core/` never reads the clock itself.
- **Reason**: Python threads cannot be forcibly killed; cooperative cancellation keeps core pure.

### D-010 — Finding `window_start` and field-match identity (R3, Phase 5-6)
- **Decision**: `window_start` is always a real ISO timestamp. For `field_match` findings the event
  id goes into `group_key` (e.g. `event=123`) so the unique key stays `(rule_id, group_key,
  tier_index, window_start)`.
- **Reason**: keeps a single column type and avoids a synthetic timestamp surrogate.

### D-011 — Lint suppressions (R4, all phases)
- **Decision**: use only narrow per-line or per-file ruff ignores, each with a comment explaining
  why. Never weaken or delete a test to obtain green lint/tests.
- **Reason**: safety rules must remain visible and auditable.

### D-012 — Client-generated passwords (R5, Phase 17)
- **Decision**: passwords generated client-side must satisfy the server policy (≥ 12 chars,
  common-password rejection); add a test covering client/server alignment.
- **Reason**: avoid one-time passwords the server would reject.

---

## Bootstrap deviations found while implementing Phase 0

### D-013 — Config loading is the filesystem exception in `core/` (Phase 0)
- **Decision**: `core/config.py` opens the TOML file in `load_settings`, while all parsing,
  merging and validation accept injected values (`env`, `root`, `config_path`).
- **Reason**: spec 00 explicitly places the loader in `core/config.py`, although the master prompt
  otherwise requires `core/` purity. The I/O surface is one function.
- **Alternatives**: move the loader to `storage/` (rejected — contradicts the spec and the static
  config split).

### D-014 — Local timezone discovery (Phase 0)
- **Decision**: `core/timeutil._local_tzinfo()` reads the host's current UTC offset through the
  single allowed clock entry point `utc_now().astimezone()`; callers can inject `tz`, and syslog
  year inference accepts an injected `now`. Config accepts only `local` and `UTC`.
- **Reason**: testability without a third-party timezone library; no DST-aware zone is stored.
- **Limit**: "local" is the offset at call time, not a named IANA zone.

### D-015 — `tmp_db` fixture (Phase 0)
- **Decision**: returns a path only; no schema is created until `storage.init_db` exists in Phase 2.

### D-016 — Phase-gated Makefile targets (Phase 0)
- **Decision**: `api`, `engine`, `web`, `web-test`, `web-e2e`, `demo` and `openapi` print a clear
  phase notice until their delivering phase; they are not silent no-ops and contain no TODO
  markers. `api`/`engine` are activated in Phase 12/11 respectively, `demo` in Phase 18.

### D-017 — Ruff excludes docs and specs (Phase 0)
- **Decision**: `extend-exclude = ["specs", "docs", "web", ".opencode"]` for ruff; those trees
  contain illustrative Python snippets, not product code. Product-code ignores remain narrow
  (D-011).

### D-018 — Open items to resolve in later phases
- Next.js exact version to be pinned in Phase 13 (D table above).
- No web CI job until Phase 13 (D-007).
- MITRE technique names to be verified against attack.mitre.org when network access is allowed
  (spec 07); otherwise recorded here as unverified.

### D-019 — `validate_event` tolerance (Phase 1)
- **Decision**: validation ignores unknown keys (so records with storage bookkeeping columns stay
  valid) and validates `severity_source` only as a string. Later phases constrain its values:
  `fallback` is treated as `default` and allowlist lowering uses `allowlist:<id>` (D-003).
- **Reason**: the spec lists type checks but no enum check for `severity_source`; strictness there
  would conflict with D-003 and with storage-added fields.

### D-020 — Deterministic naive timestamp conversion (Phase 1)
- **Decision**: keep the spec's exact `normalize_event(raw)` signature. Tests patch
  `core.timeutil._local_tzinfo` to inject the local offset instead of adding a `now` parameter.
- **Reason**: no unrequested API surface; core purity preserved.

### D-021 — Alias precedence (Phase 1)
- **Decision**: a canonical field wins over its aliases when it has a non-empty value; aliases are
  used only when the canonical field is absent or empty.

### D-022 — Canonicalization input (Phase 1)
- **Decision**: `canonicalize` validates its input, excludes only `severity`, `severity_source` and
  `enrichment`, and retains any other keys (normalization has already dropped unknown ones).
  Key order does not affect the hash.

### D-023 — Test temporary paths vs workspace isolation (Phase 1)
- **Decision**: tests continue to use pytest's `tmp_path` fixture, which lives outside the project
  tree, because AGENTS.md safety rule 5 and every phase spec mandate it. No agent-directed file
  access occurs outside the project root.
- **Reason**: resolves the tension between the added workspace-isolation rule and the mandatory
  test-isolation rule in favour of both being satisfied (isolated tests, no agent access outside).

### D-024 — Reviewer-confirmed deferrals (Phase 1)
- The indirect clock dependency in `normalize_event` (via `core.timeutil.to_utc_iso`) is the
  documented D-014/D-020 exception, not a purity breach: no clock, DB or filesystem is imported
  into the new `core/` modules.
- `severity_source` string-only validation is deferred to Phase 4 per D-019; master 4.1 lists no
  enum check, and D-003 defines the later value handling.

### D-025 — Storage filters and deferred incident join (Phase 2)
- **Decision**: `search` queries `json_extract(event_data, '$.description')` because `description`
  is not a promoted column. An `incident_id` filter raises `ValueError` with a clear message until
  Phase 7 adds the incident schema; it is never silently ignored.
- **Reason**: honours the promoted-column list in master 4.4 and avoids false query results.

### D-026 — Keyset cursor format (Phase 2)
- **Decision**: the opaque cursor is base64url JSON `{"t": timestamp, "i": id}`; ordering is
  `timestamp DESC, id DESC`; `limit` is bounded to 1–500; no OFFSET queries are used.

### D-027 — Time-series shape (Phase 2)
- **Decision**: `event_time_series` returns `{bucket_label: count}` with UTC-suffixed labels
  (`...+00:00`). With `zero_fill=True`, gaps between `since`/`until` (or the observed min/max) are
  filled with zero. Buckets are hour/day only.

### D-028 — Event write surface (Phase 2)
- **Decision**: `save_event`/`save_events` accept `severity_source` and `allowlisted` keywords,
  persist only normalizer-allowed keys, and compute identity with the severity-independent hash.
  A re-save with a different `severity_source` is deduplicated rather than creating a second row.

### D-029 — Narrow SQL lint suppressions (Phase 2)
- **Decision**: two per-line `# noqa: S608` comments with explanatory text cover SQL strings built
  from a whitelisted column name and from `?` placeholder markers. All values remain bound (R4).

### D-030 — Hypothesis fixture suppression (Phase 2)
- **Decision**: the save/get property test suppresses `HealthCheck.function_scoped_fixture`;
  each generated example uses a unique UUID description, so fixture reuse cannot cause collisions.

### D-031 — Migration application (Phase 2)
- **Decision**: `init_db` accepts an injectable `now` for `schema_version.applied_at`, applies each
  pending migration in its own explicit `BEGIN`/`COMMIT` transaction (SQLite does not implicitly
  wrap DDL), and never edits an applied migration.

### D-032 — Phase 2 reviewer fixes
- `search` escapes `\`, `%` and `_` and uses `LIKE ? ESCAPE '\'` so it is a literal substring test.
- `save_event` preserves an event's own `severity_source` unless a non-default value is passed
  explicitly (D-003 labels remain intact through storage).
- List-valued filters fail fast on scalars; `list_audit` bounds `limit` to 1–500; `MIGRATIONS` is a
  list as the spec shows; the `top_values` test asserts the exact ordering contract.
- Automatic audit rows for `set_setting` remain deferred to the Phase 12 API layer, which audits
  every mutation; the Phase 2 spec defines the two functions independently.

### D-033 — Collector state and journald resume (Phase 3)
- State keys are namespaced (`auth_log:<path>`, `journald:<unit>`, `dpkg:<path>`, `network:state`,
  `listening:state`, `processes:state`, `system:hour`).
- `journalctl` runs with an argument list, `check=False`, timeout 20 s. The next run's `--since`
  comes from the last processed entry's UTC timestamp; `__CURSOR__` is persisted for traceability.
  With `auth_source="both"`, hash dedup depends on identical UTC timestamps (pinned by a test, R1).

### D-034 — Phase 4 ingestion hooks (Phase 3)
- `engine/ingest.py` includes identity functions for enrichment, allowlist annotation and severity
  resolution, as the spec requires no-op pipeline steps. Phase 4 replaces their bodies; they do not
  create events or alter identities today.

### D-035 — Phase 3 gate adaptation
- `specs/03` asks for `python cli.py init && python cli.py collect`, but `cli.py` is a Phase 11
  deliverable. Phase 3 is verified through `run_collection` integration tests on a tmp DB instead;
  the CLI gate is exercised in Phase 11.

### D-036 — Filesystem metadata details (Phase 3)
- Modes are rendered as four-digit octal (`0644`); a missing path yields `exists=False` rather than
  an error. Rotation detection uses inode plus size shrink; replacement with an identical inode and
  size cannot be detected in v1 (to be listed in `docs/LIMITATIONS.md`).

### D-037 — Narrow lint suppressions in collectors (Phase 3)
- File-level `S108` in `processes.py` (literal suspicious-path markers, never opened), `S105` on the
  `PASSWORD_CHANGED` regex name, `S104` on the bind-scope classification constant, and test-only
  `S104/S108` for fake connections/executables. All are explained inline (R4).

### D-038 — Phase 3 reviewer fixes
- `journalctl` still uses an argument list and timeout 20 s, but the event timestamp now comes from
  a prefix embedded in `MESSAGE` when present; `__REALTIME_TIMESTAMP` is only the fallback. This
  makes "both"-mode dedup work on real syslog-prefixed messages (R1). The collector keeps
  `source="auth_log"` deliberately so identical lines hash identically; the `journald` taxonomy
  value remains unused in v1. Residual risk: messages without an embedded prefix can still differ
  by sub-second amounts from auth.log timestamps — to be listed in `docs/LIMITATIONS.md`.
- `collector_runs` now records `events_found` even when the subsequent save fails, and uses the
  injected `now` for `finished_at`.
- State is capped for listening (5 000 ports) and processes (5 000 entries); first-run suspicious
  events are capped by `max_process_events_per_run`. Network keeps its 20 000/24 h policy.
- The 4 096-byte line cap excludes the trailing newline; `authorized_keys` fingerprints accept
  `ssh-`, `ecdsa-` and `sk-` key types; listening ports report `tcp`/`udp` protocol labels.

### D-039 — Reviewer-confirmed Phase 3 scope notes
- `source="journald"` is intentionally unused in v1 so identical auth messages deduplicate across
  both sources (D-008/D-033); the taxonomy value remains reserved.
- `engine/ingest.py` identity hooks are the spec's explicit no-op pipeline steps (D-034), not stubs.

### D-040 — Condition DSL implementation (Phase 4)
- Raw condition documents are validated with path-aware errors before pydantic parsing; `None`
  group values from serialised models are treated as absent. Compiled regexes are cached; regex
  evaluation is bounded to 500 characters; `cidr_in` skips invalid CIDR strings at evaluation.

### D-041 — Seeded listening overrides (Phase 4)
- The spec's single listening override carries two severities; each override has exactly one, so
  two consecutive built-ins (`listening-all-interfaces` priority 7, `listening-loopback` priority 8)
  are seeded (D-041).

### D-042 — Storage ownership of Phase 4 config (Phase 4)
- The editable-default/override/allowlist repositories live in `storage/severity_repository.py`
  rather than overloading `storage/repositories.py`. Every mutation audits before/after in the
  same transaction, as AGENTS.md requires.

### D-043 — Re-apply semantics (Phase 4)
- `reapply_severity` defaults to dry-run and updates both the promoted severity columns and the
  severity fields inside `event_data`. Hashes are unchanged because severity is excluded (D-003).
  Allowlist `lower_severity` uses `allowlist:<id>`; a disabled event type is skipped at ingestion
  with a visible warning (D-001: evidence loss must be prominent in UI/docs later).

### D-044 — Phase 4 reviewer fixes
- The nested-quantifier heuristic now detects `(a+){2,}` and `((a+))+` as well as the original
  examples; `weekday_hour_utc` converts to UTC before formatting with a fixed English weekday.
- `set_default` validates event type and points; override create/update reject duplicate priorities
  and the 200-entry cap with `ValueError` instead of surfacing a SQLite integrity error.
- Multiple matching `lower_severity` entries lower a severity once (first match wins for the
  source label), in both ingestion and re-apply. Re-apply no longer persists `id`/`allowlisted`
  bookkeeping keys into `event_data`.
- Allowlist `ip` entries match only `source_ip` (the remote initiator per master 4.1); use `cidr`
  for outbound ranges. `ip_scope` covers `source_ip`, with `destination_ip_scope` as the separate
  destination value — the seeded `success-from-public-ip` override needs source scope.
- The prominent "disabling an event type loses evidence" warning is now in `README.md` (UI warning
  lands with the severity screens in Phase 16). Seeding is initialization and writes no audit rows.

### D-045 — Enrichment classification notes (Phase 4)
- Python's `ipaddress` treats documentation TEST-NET ranges (e.g. `203.0.113.0/24`) as private;
  public-scope tests therefore use `8.8.8.8`. Suspicious-path and all-interfaces literals are
  classification markers only, covered by an explained narrow ruff ignore (R4).

### D-046 — Rule engine return shape (Phase 5)
- `evaluate_rules` returns `(findings, warnings)` rather than a bare list so reserved kinds produce an
  explicit `NotImplementedForKind` warning and are never silently skipped (spec 05 §5.4).

### D-047 — Rule-side allowlist exclusion (Phase 5)
- Ingestion records `enrichment.allowlist_suppressed` for `suppress_alerts` matches. Threshold rules
  with `scope.exclude_allowlisted=true` drop only those events; annotate/lower entries remain in
  rule inputs, so evidence suppression is scoped correctly.

### D-048 — Same-tier re-fire rule (Phase 5)
- After a tier satisfaction, the same tier re-fires only when the next window starts strictly after
  the previous window end, or when a positive cooldown has elapsed. This prevents duplicate findings
  at `cooldown_seconds=0` without weakening escalation to higher tiers.

### D-049 — Rule cycle event window (Phase 5)
- `engine/rules.run_rules` queries only events at/after `now − (max tier window + max cooldown)`.
  Historical backtests supply their own range; integration tests use a `now` adjacent to the events.

### D-050 — Backtest surface (Phase 5)
- `BacktestResult` exposes findings, severity/tier counts, groups, an hourly timeline, up to 20 sample
  events per finding and `noise_per_day`. `should_stop` is checked between groups (D-009), and the
  core function never reads the clock.

### D-051 — Phase 5 performance measurement
- 200 000 synthetic events, one 3-tier threshold rule, 20 IPs: `evaluate_threshold` completed in
  **0.751 s** (measured 2026-11-19 with the bundled venv); test budget is 30 s.

### D-052 — Reserved-kind document shape (Phase 6)
- A before-validator renames `tiers` to `z_tiers` for `baseline_metric` and top-level `conditions` to
  `meta_conditions` for `incident_meta`, so their distinct tier/condition shapes validate without
  weakening threshold rules.

### D-053 — Sequence window and evidence (Phase 6)
- `window_start` is the first evidence timestamp of step 1 (not the moment the minimum count was
  reached). Step evidence is bounded by the next step's satisfying moment; `within_seconds` is
  measured from step 1's satisfying moment. Input order never affects the result.

### D-054 — New-value history ownership (Phase 6)
- Pre-aggregated history is supplied by `engine/rules.py`, keyed by rule id and then entity; the
  pure evaluator receives it as an argument and never queries storage or the clock. Events older
  than `learning_days` relative to injected `now` are ignored.

### D-055 — Field-match identity (Phase 6)
- Findings keep a real ISO `window_start` (D-010) and put the event id in `group_key`
  (`event=<id>`); cooldown collapse uses the rule's `group_by` separately.

### D-056 — Seeded rule set completeness (Phase 6)
- All 16 built-in rules from spec 06 are seeded, documented in `docs/RULES.md`, and all points are
  labelled uncalibrated starting values. `new-outbound-destination` stays disabled by default.

### D-057 — Phase 6 reviewer fixes
- Sequence evidence windows are anchored to each step's own satisfying moment, so widely spaced
  steps keep step-1 evidence and `window_start`. A per-entity `cursor` now allows later episodes
  separated by `cooldown_seconds`; cooldown is no longer dead code.
- `reset_all_builtin_rules` restores every seeded rule and is audited. `seed_rules` honours each
  definition's `enabled` flag in the promoted column, not only in `definition_json`.
- The live rule event window includes sequence `within_seconds`; evaluators skip malformed events
  with missing/invalid timestamps. `docs/RULES.md` states that backtesting currently supports only
  threshold rules.

### D-058 — Correlation identity and weak proximity (Phase 7)
- Component identity is the earliest anchor event hash (`correlation_key`). Weak host-proximity
  links are only created when the preceding event already has a strong link in the pair set; this
  prevents a lone low-severity anchor from being absorbed into an unrelated incident merely because
  a host event followed it (worked example). Other weak kinds follow the spec table verbatim.

### D-059 — Incident creation rule (Phase 7)
- An incident is created only when a component contains a rule-triggered event or an anchor of
  severity ≥ medium. Lone low events remain visible events with no incident (D-002).

### D-060 — MITRE mapping (Phase 7)
- The 16 seeded technique IDs map through a static table with tactic ordering and an "indicative
  mapping; verify at attack.mitre.org" label. No network lookup was performed; names are treated as
  unverified until an online check is possible.

### D-061 — Incident application (Phase 7)
- `apply_incidents` inserts by unique `correlation_key`, so re-running a plan is idempotent. Merge
  marks absorbed incidents `merged` with `merged_into`; notes, status changes and assignee edits
  write audit rows in the same transaction.

### D-062 — Phase 7 reviewer fixes
- System-created `incident_events` now persist the real link's `relation_reason`/`link_strength`;
  a stale closed incident reopens as a **new** incident via a deterministic `correlation_key` suffix;
  a merge keeps the older incident id and reassociates absorbed events.
- Findings derived from `rule_triggered` events now reach planning, so titles, summaries and
  `mitre_json` are populated from contributing rules. The creation gate requires a **medium+ anchor**
  or a rule finding with `actions.create_incident` (D-002); `create_incident` is carried in the
  rule-triggered event details.
- Extending a non-open incident moves it to `open` with a status-history row; status transitions are
  enforced by `set_incident_status`. The `incident_id` event filter is implemented (D-025).
- Span-split parts without anchors are dropped; MITRE names remain unverified until online review.

### D-063 — Baseline window semantics (Phase 8)
- Hourly buckets are zero-filled over `window_days`, ending at the last completed hour; the same
  hour supplies the "current" anomaly value per spec 8.1/8.3. A single outlier barely shifts a
  168-sample baseline. `sample_count` counts buckets; maturity additionally requires the oldest
  relevant event to be at least `min_history_hours` old.

### D-064 — Test data uniqueness (Phase 8)
- Event hashes deduplicate identical events, so burst fixtures give each event a distinct
  description; otherwise 25 identical failures collapse to one stored row and no anomaly occurs.

### D-065 — Baseline storage and series (Phase 8)
- Only one summary row per metric/subject/window is stored (`m006`); `get_baseline_series` returns
  mean/std and a configurable `mean ± z·std` band for charting rather than raw hourly rows.

### D-066 — Seeded baseline rules (Phase 8)
- Five `baseline_metric` defaults are seeded and editable; `subject: "*"` expands to the top 50
  subjects by event volume. `docs/RULES.md` documents the kind and the z/min_absolute math.

### D-067 — Phase 8 reviewer fixes
- One baseline row per metric/subject/**day** is now enforced by a `UNIQUE(metric, subject, bucket)`
  key and an upsert in `save_baseline`; the day row also stores the hourly buckets so
  `get_baseline_series` can return hourly values plus the mean ± z·std band.
- Subject expansion is now the **top 50 by matching-event volume** (`subjects_for_metric`), with a
  real test; unrelated event types no longer create spurious subjects.
- Anomaly `tier_index` now follows the canonical ascending z order while the highest satisfied tier
  still wins; z-tier severities are validated and z thresholds must strictly increase.
- The generic rule engine reports baseline rules as "evaluated by the baseline cycle" instead of a
  false `NotImplementedForKind`; `docs/RULES.md` lists all five baseline rules in the seeded table,
  and a 30-day × 50-subject performance test is included.

### D-068 — Monitored path validation (Phase 9)
- Paths must be absolute, normalised and within the allowed prefixes unless a caller explicitly
  passes `allow_custom_paths=True` (used only by tests and API input). `/etc/shadow` and
  `/etc/gshadow` are always forced to `metadata_only=true`; those files are stat-only and never
  opened or hashed.

### D-069 — Drift descriptions and flags (Phase 9)
- Comparisons produce structured changes plus exact, content-free sentences (modes, ownership,
  directory entries and key fingerprints). Flags are derived from mode bits and ownership, and
  `only_mtime` is explicit. Authorized-key snapshots store fingerprints only.

### D-070 — Drift baselines (Phase 9)
- `drift init` records one baseline snapshot per enabled path only when none exists; `drift check`
  compares against the previous snapshot so a change is reported once, and approval creates a new
  baseline snapshot with an audit row. The monitored file is never modified.

### D-071 — Limitations documentation (Phase 9)
- `docs/LIMITATIONS.md` records polling gaps, no inotify in v1, capped hashes, unprivileged read
  limits, uncalibrated points, indicative MITRE mapping and threshold-only backtesting.

### D-072 — Phase 9 review decisions and deferrals
- `check_drift` seeds both severity defaults and monitored paths, so it works standalone on a fresh
  DB. `DriftReport.warnings` no longer double-prefixes paths (the collector already does).
- `allow_custom_paths` is a real static setting (`[drift]` in `config/settings.toml`) read by
  `add_monitored_path` unless the caller overrides it explicitly.
- The service user's `~/.ssh/authorized_keys` cannot be known at seed time without resolving the
  service account; it must be added by API/CLI at deployment. Deferring it here.
- Snapshot retention ("baseline + last 200 per path") is deferred to the Phase 11 retention cycle.
- `--force` path overwrite has a boolean in the engine; an explicit confirmation belongs to the
  Phase 11 CLI and Phase 12 API.
- Added tests for real key fingerprints, symlink target changes, shadow forced metadata-only on
  reset, monitored-path reset and baseline_status transitions.

### D-073 — Risk scoring model (Phase 10)
- One distinct rule contributes its highest tier once; the raw score is capped at 100 and severity
  is `max(score band, rule floor)`. Thresholds live in `app_settings.risk.severity_thresholds`, are
  validated as strictly increasing 1–100 and are uncalibrated starting values. Summary and caveat
  reasons carry zero points so the sum of reason points equals the raw score.

### D-074 — Incident-meta rules (Phase 10)
- Four seeded `incident_meta` rules cover distinct event types, credential-to-privilege chains,
  anomalies and drift after access. All conditions are ANDed over the incident aggregate; the total
  seeded rule count is 25.

### D-075 — Recency decay floor (Phase 10)
- Decay is off by default. When enabled, contributors older than seven half-lives drop the incident
  to `low` unless it is open and a rule floor applies; a critical finding never decays below
  `medium` so a severe observed finding is not hidden by age alone.

### D-076 — Risk propagation (Phase 10)
- Assessments are upserted by `(target_type, target_id)`; incident score/severity are updated in the
  same cycle and a severity-change record is written only when severity actually changes, for later
  notification/SSE use. `explain_score` renders the stored reasons as bullet lines.

### D-077 — Phase 10 reviewer fixes
- Recency decay now keeps the rule floor for open incidents with stale findings (critical never
  falls below medium for closed ones); the rationale is documented in `docs/RISK_RULES.md`.
- Assessment upsert, incident score/severity propagation and severity-change insertion now happen in
  ONE transaction (`apply_assessment`). Scoring loads **all** findings for an incident, not just the
  100 newest.
- Rule-floor reasons identify the deciding rule and tier; thresholds reject missing keys and
  non-increasing values; incident-meta rules validate metric and op at creation time; `m008` seeds
  the two `app_settings` keys; `explain_score` no longer repeats the tier label.

### D-078 — Pipeline layering (Phase 11)
- `core/pipeline.run_cycle` receives its steps via injection (with timing/isolation) so it does no
  I/O; `engine/runner.default_steps` supplies the concrete collect → rules → baselines → correlate →
  score → notify → publish steps. Failed steps are recorded and never stop later steps.

### D-079 — CLI deferrals (Phase 11)
- `user` commands require the auth tables from Phase 12 and `demo` arrives in Phase 18; both are
  explicit commands with exit code 2 and a clear message, not silent stubs. `getpass` is used for
  passwords, never argv.

### D-080 — Notification safety (Phase 11)
- Outbound delivery is off unless `notifications.enabled` is true; channels are admin-editable in
  the DB with secret **env-var names** only. Webhook HMAC uses that env var, SMTP requires STARTTLS
  unless explicitly disabled, transports have timeouts and bounded retries, and tests use fakes only.

### D-081 — Retention (Phase 11)
- `plan_prune` is pure, dry-run is the CLI default, evidence linked to an incident is protected,
  baselines are always kept and audit rows are pruned last; every application writes an audit row.

### D-082 — Phase 11 review and security fixes
- Retention now performs real chunked deletes using per-severity ages, protects events linked to
  open/investigating incidents and writes an audit row only after deletion. `--dry-run` remains the
  default; `--apply` is explicit (`--dry-run` is a harmless alias).
- The engine loop uses real sleeps, derives backoff from the cycle report, tracks both intervals and
  installs SIGTERM/SIGINT handlers; `setup_logging` is installed at the CLI entrypoint and creates
  the log directory.
- Notifications now use real delivery history for cooldown/rate limits, deduplicate per channel and
  trigger, include incident-created as well as escalation triggers, honour BOTH the static TOML flag
  and the DB flag, and implement Telegram. Webhook URLs are validated with `urlparse` (loopback
  HTTP or explicitly allowed HTTPS hosts), require a non-empty env secret, and use `config["url"]`;
  SMTP uses a verifying TLS context. Retry attempts no longer sleep in the inline cycle.
- `rules backtest` is wired, `severity set` preserves points, `m009` gains indexes and
  `notification_log.finding_id`. HMAC and `run_notifier` kill-switch tests were added.
- Deferred (non-blockers): finding-level `actions.notify` triggers, full export sections/status
  history, and moving the spec-mandated `core/health`/`export` clock+I/O exceptions out of `core`.

### D-083 — API security foundation (Phase 12)
- `m010` creates users/sessions/saved_filters as planned (G1). The API refuses to start without
  `SENTINEL_SESSION_KEY` (D-006). CSRF tokens are HMACs of the session id; unsafe methods also check
  Origin. Roles are enforced server-side; CLI `user create` uses `getpass` and never puts the
  password in argv.
- scrypt uses the specified n=2^15/r=8/p=1 parameters; an explicit `maxmem=64 MiB` is passed because
  OpenSSL's default limit rejects the specified memory cost. Verification is constant-time and
  unknown usernames are checked against a precomputed dummy hash for uniform timing.

### D-084 — API contract (Phase 12)
- `web/openapi.json` is the committed contract, regenerated with `make openapi`; a test asserts it is
  current. Errors use the `{error:{code,message,details?}}` envelope, pagination is keyset-based,
  and routers stay thin (validate → call → serialize).

### D-085 — Phase 12 review and security fixes
- `make api` and `cli.py api` now serve the app; the non-loopback guard requires `allow_remote` and
  a `trusted_proxy` note, and session keys shorter than 32 characters are rejected at startup.
- The remaining catalogue endpoints were added (override CRUD/reorder, risk decay, allowlist
  update/stats, drift path update/delete/status/history/check, notification channel
  update/delete/test, rules import/export, user password reset). SQL moved out of routers into
  storage helpers; incident list, timeline findings and event detail links were fixed.
- Login failures are now uniform in body and timing for unknown, wrong-password, locked and
  disabled accounts; throttling counts username and IP with exponential lock repeats; passwords are
  rehashed when scrypt parameters change. Sessions touch `last_seen` on authenticated requests.
- SSE is a bounded streaming loop with 15 s heartbeats and a per-user connection cap. Request body
  caps (1 MB / 2 MB), per-client rate limits on expensive routes and cooperative 30 s backtest
  deadlines were added. All config/user/channel/filter mutations audit actor/before/after/IP.
- An OpenAPI-driven matrix parametrises CSRF and RBAC across every unsafe route. Tests cover
  cookie flags, hash omission, session revocation, timing, and `GET /api/incidents`.
- Deferred (non-blockers): typed request/response models for every endpoint, `mode=ro` read
  connections, markdown-lite sanitisation of notes, and one router module per resource area.
