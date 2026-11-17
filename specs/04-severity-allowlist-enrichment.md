# Phase 4 — Condition DSL, editable severities, allowlist, enrichment

Skills: sentinel-rules-engine, sentinel-event-schema, sentinel-sqlite-patterns, sentinel-security-hardening, sentinel-testing-workflow.

## Goal
Make "what severity does an event get?" fully data-driven and user-editable, add a visible allowlist, and add offline enrichment. Also build the shared **condition DSL** that Phases 5–6 reuse.

## 4.1 Condition DSL — `core/conditions.py` (pure)
A condition is `{"field": str, "op": str, "value": Any}`; a **condition group** is `{"all": [..]}`, `{"any": [..]}` or `{"not": cond}`, nestable to depth 4. Empty/absent = always true.

- Fields: any top-level event field, plus dotted paths into `details.*` and `enrichment.*` (e.g. `details.command_executable`, `enrichment.ip_scope`). Missing field → condition is false (except `not_exists`).
- Ops: `eq, ne, in, not_in, contains, not_contains, startswith, endswith, regex, gt, gte, lt, lte, exists, not_exists, cidr_in, cidr_not_in`.
- `in`/`not_in` take lists (max 500 items). `contains` works on strings and lists. `cidr_in` takes a list of CIDR strings, uses `ipaddress`; invalid IP → false.
- **Regex safety**: pattern length ≤ 200; compile at validation time; reject patterns with nested quantifiers (`(a+)+`, `(.*)*`, `(a|aa)+`) via a heuristic; evaluate against the first 500 chars of the field; never use user input as a format string.
- API: `validate_condition(obj) -> Condition` (pydantic model, raises `ValueError` with a path-aware message), `evaluate(cond, event) -> bool`, `describe(cond) -> str` (human text used in UI/explanations, e.g. `username is "root" AND source_ip in 10.0.0.0/8`).
- Case: string comparisons for `eq/in/contains/startswith/endswith` are case-sensitive unless the condition has `"ci": true`.

## 4.2 Event-type defaults — `core/severity.py` (pure)
Seed table (all editable by the admin; each row remembers `default_severity`/`default_points` for reset; `enabled=false` makes ingestion skip storing that type — document that disabling loses evidence):

| event_type | severity | points |
|---|---|---|
| failed_login | low | 5 |
| invalid_user | low | 5 |
| preauth_disconnect | low | 0 |
| successful_login | low | 0 |
| sudo_command | low | 0 |
| su_command | low | 0 |
| user_created | medium | 10 |
| user_deleted | medium | 10 |
| group_member_added | medium | 10 |
| password_changed | low | 0 |
| permission_change | medium | 10 |
| network_connection | low | 0 |
| new_listening_port | medium | 5 |
| process_started | low | 0 |
| suspicious_process | high | 15 |
| package_installed | low | 0 |
| package_removed | low | 0 |
| config_drift | medium | 10 |
| anomaly | medium | 10 |
| rule_triggered | medium | 0 (tier decides) |
| system_info | low | 0 |

`points` = the event's own contribution shown in event-level scores (not summed into incidents; incident scoring is rule-based, Phase 10).

## 4.3 Severity overrides (conditional, ordered)
Table `severity_overrides` (`priority` ascending, first enabled match wins). Seed (builtin, editable, resettable):
1. `failed_login-root`: `event_type = failed_login AND username = root` → medium.
2. `sudo-sensitive-command`: `event_type = sudo_command AND process_name in [visudo, passwd, useradd, usermod, userdel, chmod, chown, crontab, systemctl]` → high.
3. `drift-world-writable`: `event_type = config_drift AND details.flags contains world_writable` → critical.
4. `drift-sensitive-content`: `event_type = config_drift AND details.sensitivity in [high, critical]` → high.
5. `drift-low-mtime-only`: `event_type = config_drift AND details.only_mtime = true` → low.
6. `success-from-public-ip`: `event_type = successful_login AND enrichment.ip_scope = public` → medium.
7. `listening-all-interfaces`: `event_type = new_listening_port AND details.bind_scope = all_interfaces` → medium (keeps default) / `…bind_scope = loopback` → low.

API of the pure module:
```python
resolve_severity(event, defaults: dict[str, TypeDefault], overrides: list[Override]) -> tuple[str, str]
# returns (severity, severity_source) with source "override:<id>" | "default" | "fallback"
```
Validation: severities in the valid set; priorities unique ints; at most 200 overrides; conditions validated by the DSL. Editing defaults/overrides: stored in DB through repositories, written to `audit_log`, never rewrites existing events by itself.

**Re-apply** (`storage`/`engine`): `reapply_severity(filters, db_path, dry_run=True)` recomputes severity for stored events (batch, transactional), updates `severity` + `severity_source`, returns `{examined, changed, by_severity_before_after}`; `dry_run=True` by default; admin must confirm. Event hashes are unaffected (severity excluded).

## 4.4 Allowlist — `core/allowlist.py` (pure) + storage
Entry: `{kind: ip|cidr|username|command|event_type|path, value, scope: annotate|suppress_alerts|lower_severity, reason (required, ≥5 chars), expires_at?, enabled}`.
- `annotate`: event stored normally, `allowlisted=1`, enrichment `allowlist_match=[ids]`.
- `suppress_alerts`: events still stored and visible, but excluded from rule evaluation inputs, incident creation and notifications. The UI shows a suppressed counter and lets the admin see them.
- `lower_severity`: severity reduced by one level (min `low`), `severity_source` records it.
- Expired entries are ignored automatically; `matches(event, entries, now) -> list[Entry]`.
- Never drop evidence. Every create/update/delete is audited. Entries without a reason are rejected.

## 4.5 Enrichment — `core/enrichment.py` (pure, offline)
`enrich_event(event) -> dict` adds `enrichment`: `ip_scope` for `source_ip`/`destination_ip` (`loopback|private|link_local|public|invalid`) via `ipaddress`; `is_root_user`; `suspicious_path`; `bind_scope`; `is_service_account` (username matches `^(daemon|www-data|nobody|systemd-.*|_.*)$`); `weekday_hour_utc` (for time-of-day rules). No DNS, no GeoIP, no network. Never mutates existing fields.

## 4.6 Ingestion integration
In `engine/ingest.py`, per event: normalize → enrichment → allowlist → severity resolution (overrides → defaults) → skip if type disabled → hash (excluding severity/enrichment) → save with `severity_source` and `allowlisted`.
Migrations `m003` (`event_type_defaults`, `severity_overrides`, `allowlist_entries`) and **seeding** (`seed_defaults(db_path)` inserts missing rows only; never overwrites user edits; `reset_*` functions restore a single item or all).

## Worked example
```python
# User edits failed_login default to "medium" and adds override "failed_login-root" → high
resolve_severity({"event_type":"failed_login","username":"root", ...}, defaults, overrides)   # ("high","override:failed_login-root")
resolve_severity({"event_type":"failed_login","username":"bob",  ...}, defaults, overrides)   # ("medium","default")
reapply_severity({"event_type":["failed_login"]}, dry_run=True)   # {"examined": 4200, "changed": 4200, ...}
```

## Tests
DSL: every op, nesting, `not`, missing fields, dotted paths, `ci`, regex length/nested-quantifier rejection, CIDR v4/v6/invalid, depth limit, `describe` text, hypothesis (random conditions never raise on random events). Severity: defaults table complete for every event type; override precedence and priority ties rejected; disabled override skipped; fallback; source labels. Reapply: dry-run changes nothing; real run updates; hash unchanged; large batch transactional. Allowlist: each kind/scope, expiry boundary, reason required, suppressed events stored and flagged, lower_severity floor. Enrichment: IP scopes (incl. IPv6, malformed), suspicious path, bind scope. Seeding idempotent and never overwrites edits; reset restores defaults; audit rows written. Integration: collect → events carry resolved severities.

## Gate
Suite green; `mypy` strict on `core/conditions.py`, `core/severity.py`, `core/allowlist.py`, `core/enrichment.py`.
