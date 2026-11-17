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
