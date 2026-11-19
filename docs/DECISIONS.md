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

### D-086 — TestClient dependency (2026-11-19)
- Added `httpx2` 2.16.2 to the dev dependencies (with `httpcore2` 2.16.2 and `truststore`
  0.10.5) so Starlette 1.10.0's `TestClient` uses the supported client and no longer emits
  `StarletteDeprecationWarning`. Approved by the user; production dependencies are unchanged.
- Trade-off: the API test suite is slower (~61 s vs ~34 s) with `httpx2`.

### D-087 — Web toolchain versions (Phase 13)
Node `v24.22.1`, npm `11.19.1`. Exact pinned versions (commit `web/package-lock.json`):
Next.js `16.4.6`, React/ReactDOM `19.3.1`, TypeScript `5.9.3` (strict +
`noUncheckedIndexedAccess`), Tailwind CSS `4.3.5` with `@tailwindcss/postcss` `4.3.5`,
PostCSS `8.5.33`, `@tanstack/react-query` `5.108.0`, `@tanstack/react-table` `9.3.1`,
Recharts `3.11.0`, react-hook-form `7.92.0`, zod `4.6.7`, `@hookform/resolvers` `7.0.7`,
openapi-typescript `7.13.0`, openapi-fetch `0.17.0`, date-fns `4.4.0`, date-fns-tz `3.2.0`,
lucide-react `1.76.0`, clsx `2.1.1`, tailwind-merge `3.7.0`, class-variance-authority `0.7.1`,
`@radix-ui/react-slot` `1.5.0`; dev: Vitest `5.1.1`, Vite `8.3.8`, `@vitejs/plugin-react`
`6.3.0`, Testing Library React `16.3.3`, jest-dom `8.0.0`, user-event `14.6.13`, MSW `3.0.7`,
jsdom `31.0.1`, Playwright `1.65.1`, ESLint `9.39.5`, `eslint-config-next` `16.4.6`,
`eslint-plugin-jsx-a11y` `6.10.2`, `eslint-config-prettier` `10.1.8`, Prettier `3.10.1`,
`@types/node` `26.6.6`, `@types/react`/`@types/react-dom` `19.3.0`. ESLint is pinned to 9.x
because `eslint-plugin-jsx-a11y` 6.10.2 does not accept ESLint 10 as a peer. No other packages
were added. `frontend-design` skill was not available and was not required.

### D-088 — API client and SSE fallback (Phase 13)
- `lib/api/schema.d.ts` is generated from `web/openapi.json` with `npm run gen:api`; the client
  is `openapi-fetch` with `credentials: "include"`, dynamic `X-CSRF-Token` from the readable
  cookie on unsafe methods, envelope→`ApiError` mapping and a `sentinel:unauthorized` event on
  401. No tokens are written to `localStorage`. The client resolves `fetch` at call time so
  unit tests can stub it.
- `middleware.ts` redirects to `/login?next=` when the session cookie is absent and builds a
  nonce-bearing CSP; the login screen validates `next` with `validateNextPath()` (same-origin
  absolute paths only) before navigating. `Content-Security-Policy`
  therefore lives in middleware (not `next.config`) to avoid duplicate policies; Next receives
  the nonce through the `x-nonce` request header.
- Next.js 16.4.6 prints a deprecation notice for the `middleware.ts` convention in favour of
  `proxy.ts`. The file is kept as `middleware.ts` because spec 13.3 names it explicitly; the
  redirect and CSP behaviour was verified by starting `make web` and requesting `/login` and
  `/events` (307 to `/login?next=%2Fevents`, all security headers, no `x-powered-by`).
- SSE through a buffering proxy cannot be verified in a single-process test environment, so the
  polling fallback is implemented proactively: after three stream failures `useLiveUpdates()`
  polls `GET /api/changes?since=` every 10 s. That endpoint was added to the API in this phase
  with a test. The SSE stream itself remains the preferred path.

### D-089 — Phase 13 manual checklist (screenshot-free)
Run `make api` and `make web`, then verify by hand (no screenshots):
1. `curl -I http://127.0.0.1:3000/login` shows `content-security-policy` with `frame-ancestors 'none'`,
   `x-content-type-options: nosniff`, `referrer-policy: no-referrer`, `x-frame-options: DENY`,
   `permissions-policy`, and no `x-powered-by`.
2. `curl -I http://127.0.0.1:3000/events` without cookies returns 307 to `/login?next=%2Fevents`.
3. Login with the seeded demo admin, confirm the shell, the "Live updates active" indicator,
   and that role-hidden admin controls appear only for admins; sign out returns to `/login`.
4. Toggle the theme and reload; the choice persists. Open a table and confirm its filter is
   reflected in the URL query string.
5. Confirm `GET /api/changes?since=0` returns `{items, next_cursor}` only for authenticated
   sessions, and that a viewer receives 403 on a mutating endpoint even with a valid CSRF token.

### D-090 — Phase 13 security audit notes
- Hardened in this phase: `/api/changes?since=` and `Last-Event-ID` are bounded to signed 64-bit
  ids; `validateNextPath()` keeps structural checks even without `window`; web responses outside
  `/_next` send `Cache-Control: no-store`; a 401 clears the TanStack cache before redirecting.
- `secure_cookies = true` in `[api]` is mandatory behind an HTTPS reverse proxy; the default is
  false for loopback development. The SSE per-user connection cap is per worker (global cap
  belongs at the proxy). Login remains exempt from CSRF because no session exists yet; Origin
  checking for login is a Phase 12 issue (login CSRF cannot create a foothold without
  self-registration). Lockout is intentionally a uniform 401 rather than a 429 with `retry_after`
  so it cannot disclose account state; the UI's 429 branch covers a future pre-auth limiter.

### D-091 — Phase 13 reviewer fixes
- Added `web/playwright.config.ts` (baseURL, Chromium project, webServer). `npm run test:e2e`
  still requires the API and the seeded demo database from Phase 18; it is not part of CI.
- `DataTable` now wraps TanStack Table v9 (`useTable`, `tableFeatures`,
  `createFilteredRowModel`) instead of hand-rolling filtering. v9 removed the v8
  `useReactTable`/`getCoreRowModel` exports, so the v9 API is used directly.
- Polling status is reported as `polling` (never as `live`), polling timers are stopped when a
  stream reconnects, and the SSE frame id (change-row id) is used for `since=`.
- Added the toast region, field-level server-error mapping with an unsaved-changes guard, a
  change-password dialog, `JsonViewer`, risk thresholds read from `/api/risk/thresholds`,
  locally stored display timezone, and a factual "highest incident score" on Overview.
  `date-fns-tz` is now used for absolute timestamps. CI runs `make coverage`.
- `web/AGENTS.md` and `web/tsconfig.tsbuildinfo` are generated by `next dev`/`tsc` and ignored.

### D-092 — Phase 14 API support and demo seed
- `storage/database.py` registers a parameterised `ip_in_cidr` SQL helper so `/api/events` accepts
  `source_cidr` (IPv4/IPv6, strict=False) without moving filtering into the router. Invalid CIDRs
  simply never match. CIDR validity is also checked client-side before the filter is shared.
- `/api/events/stats?group_by=severity` returns zero-filled `{buckets:[{bucket,severity,total}]}`
  for stacked charts; the previous total-only shape is unchanged when `group_by` is absent.
- `/api/events/export` now accepts the same filter parameters as `/api/events` and is bounded at
  100 000 rows via `query_events_bulk`; the UI states the cap. The seed script
  `scripts/seed_demo_db.py` is deterministic, idempotent, writes only to the requested DB path,
  and refuses monitored system paths. Its `admin`/`viewer` accounts use the demo-only password
  `demo-password-123` (override with `SENTINEL_DEMO_PASSWORD`) and must never be used in production.

### D-093 — Phase 14 UI decisions
- Filter state is owned by the URL (`filtersToSearch`/`parseEventFilters`) and never stored in
  localStorage. "Include allowlisted" defaults on (badge shown); switching it off sends
  `allowlisted=false` to the API, which excludes allowlisted events.
- Live mode uses a 10 s TanStack refetch and a "N new events — click to load" banner only when the
  user has scrolled; the SSE-backed `LiveFeed` on Overview keeps its own pause/resume control.
- Response payloads for these endpoints are still untyped `dict` in the generated schema, so the
  UI uses small structural projections (`EventLike`, `StatBucket`, `SavedFilter`) rather than
  duplicating full API models. All endpoints are still called through the generated typed client.
- `@axe-core/playwright` was not added because no new dependency was approved; Playwright specs
  cover the journeys and WCAG semantics are checked by the `jsx-a11y` ESLint rules.

### D-094 — Phase 14 reviewer fixes
- `useLiveUpdates({paused})` truly stops the stream; Overview's pause button now controls both
  status and refetching, and new live rows are highlighted briefly with reduced-motion support.
- "Only in incidents" uses a server-side `in_incident` filter (events in **any** incident) rather
  than a hard-coded incident id. `query_events` now returns a filtered `total`, used by the KPIs
  instead of a 500-row sample.
- Presets are expanded to absolute `since`/`until` when parsed from the URL, and every Overview
  KPI/top-list link carries an explicit range. FilterBar gained source multi-select, process and
  custom-time controls with a UTC/local toggle; text search is debounced by 250 ms.
- HealthStrip shows last-cycle age, DB size and collector status; the event drawer receives real
  related findings/incidents and closes on Esc; the saved-filter button is wired; QuickStats shows
  the matching total. Tests cover pause, preset expansion, the any-incident toggle and KPI retry.
- Re-review found two export regressions, both fixed: the default URL no longer sends
  `allowlisted=true` (which the API reads as *only* allowlisted events), and `in_incident` is
  forwarded to `/events/export` so the downloaded file matches the visible table. A regression
  test asserts the exact query string for both cases.

### D-095 — Phase 15 API and demo scenario
- `list_incidents_page` adds keyset pagination with `risk`/`recent` sort and the documented filters
  (`status`/`severity` lists, time range, assignee, text, `needs_attention`). The incident endpoint
  returns `{items,next_cursor}`; `useIncidents` still normalises older list responses so existing
  pages keep working.
- Added `GET /api/incidents/{id}/history` (status history plus related audit rows) and
  `POST /api/incidents/bulk-status` (admin only, 1..500 ids, transition/reason validation).
  `explanation` now includes the incident's rule findings; `graph` returns entity nodes with counts
  and link reasons instead of raw event-id endpoints. Export returns a real `application/pdf`
  response with a `Content-Disposition` filename for PDF, and text/JSON for the other formats.
- `scripts/seed_demo_db.py` now creates one deterministic standard scenario incident with four
  evidence events, a finding, a note, a status change and a stored assessment (85/high), so the
  Playwright incident journeys have stable data. It remains idempotent and workspace-scoped.

### D-096 — Phase 15 UI decisions
- `lib/incident/helpers.ts` holds the pure arithmetic and layout: `whatIfScore` mirrors the server's
  capped sum and severity-basis logic (verified against the Phase 10 worked example: 170 → 100),
  `layoutGraph` is order-independent, `collapseRepeats` keeps first/last timestamps, and
  `sanitizeMarkdown` renders only bold/inline-code/safe links so notes cannot inject HTML.
- The caveat is rendered by the incident header so it is visible on every tab and deep link.
  The what-if panel is explicitly labelled "simulation, not saved"; inferred entries and weak
  relations carry both text and styling. Status changes surface 409 as "Incident changed, reload".
- Response payloads remain untyped dicts in the generated schema; small structural projections
  (`IncidentRecord` extensions, `ScoreReason`) are used instead of hand-copied API models. No new
  dependency was added; the entity graph is plain SVG.

### D-097 — Phase 15 reviewer fixes
- Status changes carry an optional `updated_at`; a stale value returns 409 `conflict`, the client
  updates optimistically with rollback, and only a real 409 shows "Incident changed, reload".
- The timeline collapses consecutive observed repeats into expandable "×N … between …" summaries
  and offers "Show all N entries" above 2 000 rows; SSE `incident.*` messages highlight changed
  incident rows for three seconds.
- Stored findings are normalised before entering the timeline (evidence ids, explanation, tier),
  `explain_incident` returns anchor events, inferred entries cite evidence and highlight it on
  hover, and the explanation panel lists anchors.
- Markdown/JSON/PDF exports now include the timeline, score reasons and notes. `rules_fired` is
  derived from findings (top 3) and the Evidence tab lists finding rows with per-row actions.
- Also added: incident time-range inputs, assignee editing and duration, a real "Copy summary",
  audit entries in history, RBAC coverage for the new admin endpoints, and `core/export.py`
  tolerance for string MITRE ids (demo seed data).
- Re-review found two remaining gaps, both fixed: expanding a collapsed repeat now renders its
  member events, and incident create/status/assignee/note mutations write `changes` rows so the
  live feed emits `incident.*` events; the polling fallback also forwards messages to the highlight
  callback. Both have regression tests.
- Final re-review caught one more detail: the polling fallback now forwards `ref_id` (the incident
  id) rather than the change-row `id` to the highlight callback, with a dedicated test.

### D-098 — Phase 16 rule API additions
- `/api/rules/schema` now publishes the field catalogue (including `details.*` and `enrichment.*`),
  operators, event types, group-by fields, kinds, severities, window modes, MITRE catalogue and
  limits, so the builder is driven by the server catalogue rather than duplicated constants.
- `/api/rules/export` exports all stored rules (not only built-ins). `/api/rules/import` validates
  each document before creating it and returns `{created, errors}` with document paths, so the UI
  can show per-field errors. `POST /api/rules/{id}/versions/{version}/restore` creates a **new**
  version from an older definition; history is never rewritten and the action is audited.

### D-099 — Phase 16 UI decisions
- `web/lib/rules/helpers.ts` contains the pure builder logic: tier window conversion, the exact
  sentence preview required by the spec, `describe` for conditions, lossless form↔JSON round trips,
  diffs, regex limits (200 chars, no nested quantifiers), threshold validation and server-path
  mapping. The server remains authoritative via debounced `/rules/validate`.
- The rule editor keeps form and JSON modes synchronised and blocks a switch back from invalid JSON.
  Preview/backtest is debounced, cancellable and labelled a simulation; save shows a diff dialog;
  built-in rules can be reset and any version restored. Unsaved changes are guarded.
- Severity defaults are edited locally then saved in one batch; overrides use keyboard-accessible
  reorder controls (mouse reorder uses the same handler) with condition editing and a test box;
  re-apply requires a typed confirmation and explicitly states that defaults affect new events only.
  Allowlist entries require a reason and convert relative expiries to ISO-8601 ("never" warns); the
  stored-evidence banner is always shown.
- The builder uses react-hook-form + zod for client-side field validation, while the server remains
  authoritative. Server `details[].path` messages are shown inline and passed to the tier editor.
- No new dependencies were added. Rendered definitions never include file contents or secrets, and
  all mutation controls are hidden from viewers while the API independently enforces RBAC.

### D-100 — Phase 16 review/security fixes
- Regex validation rejects more than two unbounded quantifiers in addition to nested quantifiers,
  the compiled-pattern cache is bounded to 128 entries, and the threshold evaluator checks the
  cooperative deadline inside its event loop. Both Python and client validators share the rule
  (test pattern `.*.*.*.*.*.*Z`).
- The rule editor now uses react-hook-form + zod, fetches the server catalogue directly, mirrors
  server validation paths into inline field errors, and covers all six rule kinds. Duplicating a
  rule loads its stored definition first; delete/reset/restores and allowlist deletion require
  confirmation. Severity defaults are editable and batch-saved; "reset all" requires a typed
  phrase; overrides support conditions, reordering by mouse/keyboard, a test box and CRUD.
- Import rejects duplicate ids with a path-aware error and caps lists at 100 documents; inverted or
  malformed backtest ranges return 422. Allowlist relative expiries are converted to ISO-8601.
  The authoritative docs/RULES.md content was restored and the builder walkthrough appended.
- Re-review fixes: the event-type `enabled` flag is now persisted on batch save; every non-threshold
  kind builds a server-valid definition (sequence steps, baseline z-tiers, meta conditions,
  new-value fields) with an optional-tiers zod schema; the override test box calls a new
  read-only `POST /api/severity/overrides/test` endpoint and shows the resulting severity/source,
  and override rows carry badges/conditions with create and duplicate actions.
- Final re-review: `baseline_metric` now emits z-tier objects under the canonical `tiers` key (the
  server reshapes on key presence), the zod schema accepts both tier shapes, and a helper unit test
  covers the UI-shaped definition.

### D-101 — Phase 17 API support
- `/api/system/info` now reports the global notification switch, schema version, engine intervals
  and **booleans** for known secret environment variables (never their values). Channel config keys
  ending in `_env` must be uppercase environment variable names (`^[A-Z][A-Z0-9_]{2,63}$`).
- `/api/audit` supports actor/action-prefix/target-type/time filters and keyset cursors;
  `POST /api/users/{id}/sessions/revoke` revokes a user's sessions. Disabling or demoting the last
  active admin returns 409 and is audited. All Phase 17 writes use existing CSRF/RBAC middleware.

### D-102 — Phase 17 UI decisions
- `web/lib/admin/helpers.ts` owns pure band/zero-fill math, maturity wording, env-name validation,
  audit before/after diffs, password strength, retention validation and health hints. Immature
  baselines explicitly say "Not enough data yet — no anomalies will be reported", never "all clear".
- Drift pages render snapshot metadata only (mode, owner, hash prefix, flags) — never file contents;
  shadow paths show a locked metadata-only control. Accepting a baseline requires a reason and
  states that only Sentinel's reference changes.
- Notification secret inputs are env-var **names** with a set/not-set indicator; display settings
  live in `localStorage`; user creation shows a generated one-time password; audit CSV escapes
  formula-leading cells. Viewer pages are read-only and mutation controls are disabled.
- No new dependencies were added; every page uses the generated typed client.

### D-103 — Phase 17 reviewer fixes
- Dict-returning endpoints (`/system/info`, `/settings/retention`, `/health`) are read through
  dedicated hooks, not the generic `useApiList` dict-to-rows adapter; the notifications, settings and
  health pages now display real values.
- The retention form edits the nested `policy.events` ages and saves via `PUT /api/settings/retention`.
  Viewer redirects, hidden admin links, read-only channel editors, stricter baseline-accept reasons,
  extended RBAC coverage and audited session revocation were added. Immature baselines always carry
  the explicit "no anomalies will be reported" caveat.
