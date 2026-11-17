# Phase 5 — Rules engine core (models, storage, threshold evaluator, backtest)

Skills: sentinel-rules-engine, sentinel-explainability, sentinel-sqlite-patterns, sentinel-testing-workflow.

## Goal
Let the administrator define detection rules such as:

> Failed logins grouped by source IP: **≥ 5 within 10 minutes → medium**, **≥ 20 within 10 minutes → high**, **≥ 50 within 60 seconds → critical**.

Rules are data (validated JSON), versioned, enable/disable-able, backtestable and resettable. Evaluators are pure functions. This phase builds the model, persistence, threshold evaluation and backtesting; Phase 6 adds the other kinds.

## 5.1 Rule document (pydantic v2 discriminated union on `kind`)
Common fields:
```json
{
  "id": "ssh-bruteforce-by-ip",            // slug [a-z0-9-], 3-64 chars, unique
  "name": "SSH brute force from one IP",
  "description": "Repeated failed logins from the same source IP",
  "kind": "threshold",
  "enabled": true,
  "match": { "event_types": ["failed_login", "invalid_user"], "conditions": { "all": [] } },
  "scope": { "exclude_allowlisted": true },
  "actions": { "create_incident": true, "notify": true, "tags": ["brute-force"] },
  "mitre": ["T1110.001"]
}
```
`threshold` kind adds:
```json
{
  "group_by": ["source_ip"],
  "aggregate": { "type": "count" },                       // or {"type":"distinct_count","field":"username"}
  "window_mode": "sliding",                               // "sliding" | "fixed"
  "fixed_alignment": null,                                // for "fixed": "minute"|"hour"|"day"
  "cooldown_seconds": 900,
  "tiers": [
    { "label": "Repeated failures",  "count": 5,  "window_seconds": 600, "severity": "medium",   "points": 15 },
    { "label": "Sustained attack",   "count": 20, "window_seconds": 600, "severity": "high",     "points": 30 },
    { "label": "Burst",              "count": 50, "window_seconds": 60,  "severity": "critical", "points": 45 }
  ]
}
```
Validation rules (all produce path-aware errors the UI can show next to the field):
- `id` slug; `name` 3–80 chars; description ≤ 500.
- `match.event_types` non-empty subset of known types (cannot include `rule_triggered`, `anomaly` unless explicitly allowed by kind).
- `group_by` ⊆ {`source_ip`, `username`, `process_name`, `destination_ip`, `file_path`, `source`} and may be empty (= global).
- `tiers`: 1–10; `count` 1–100 000; `window_seconds` 10–2 592 000 (30 days); `points` 0–100; severity valid; labels unique; no two tiers identical in `(count, window_seconds)`; **monotonicity warning** (not an error): a tier with a larger-or-equal count and window≥ but lower severity than another tier is dominated — return a warning list from `validate_rule()` so the UI can display it.
- `cooldown_seconds` 0–604 800. `window_mode="fixed"` requires `fixed_alignment`; all tiers' windows must then equal the alignment length (minute=60, hour=3600, day=86400) — otherwise error.
- `aggregate.field` for `distinct_count` must be a promoted/known field or a dotted `details.*` path.
- Unknown keys rejected (`extra="forbid"`).
- `validate_rule(obj) -> tuple[Rule, list[str]]` returns the model and warnings; raises `RuleValidationError(errors=[{path, message}])`.

## 5.2 Threshold evaluation — `core/rules/threshold.py` (pure)
`evaluate_threshold(rule, events, now) -> list[Finding]`

`Finding` dataclass: `rule_id, rule_version, group_key (stable string like "source_ip=203.0.113.45"), tier_index, tier_label, severity, points, window_start, window_end, observed (int), threshold (int), window_seconds, evidence_event_ids (sorted list, capped at 500), explanation (str)`.

Algorithm (exact semantics):
1. Filter events by `match.event_types` + conditions; drop allowlisted-with-`suppress_alerts` events when `scope.exclude_allowlisted`; drop events with missing `group_by` fields (a rule grouping by `source_ip` ignores events without one).
2. Bucket by `group_key`; sort each bucket by `(timestamp, id)`.
3. **Sliding** mode: for each tier independently, two-pointer scan: for every event `e_i` as the window end, count (or distinct-count) events in `(t_i − window, t_i]`. The tier is **satisfied** at the first `t_i` where the count ≥ `tier.count`; record `window_start = max(t_i − window, first event in window)`, `window_end = t_i`, evidence = events in that window. Continue scanning to find later *non-overlapping* satisfactions: after a satisfaction at `t_i`, the next satisfaction for the same tier must have a window starting after `t_i` (no overlap) **or** be separated by at least `cooldown_seconds`.
4. **Fixed** mode: bucket timestamps into aligned intervals (minute/hour/day in UTC); a tier is satisfied for an interval when that interval's count ≥ `tier.count`. `window_start` = interval start, `window_end` = interval end.
5. Per group and per "episode" (satisfactions within `cooldown_seconds` of each other), **escalation**: report one finding for the highest satisfied tier by severity then points; if a higher tier is satisfied later in the same episode it produces an additional finding (escalation). A lower tier never re-fires after a higher one in the same episode.
6. Findings carry a deterministic unique key `(rule_id, group_key, tier_index, window_start)`.
7. Only the evidence needed: `evidence_event_ids` = ids of events inside the satisfying window (cap 500; `observed` keeps the true count).

Explanation text (always generated): `"5 failed_login/invalid_user events from source_ip=203.0.113.45 within 10 minutes (threshold: ≥5 in 10 min → medium). First at 10:00:03, last at 10:04:51."` with distinct-count variant `"8 distinct usernames ..."`.

## 5.3 Persistence
Migration `m004`: `rules`, `rule_versions`, `rule_findings` (see master prompt 4.4).
`storage/repositories.py` additions: `create_rule`, `update_rule` (bumps `version`, writes `rule_versions`, audit), `set_rule_enabled`, `delete_rule` (custom rules only; built-in can only be disabled), `reset_rule` (restore `default_definition_json`, bumps version), `get_rule`, `list_rules(filters)`, `save_findings(findings) -> list[(id, is_new)]` (INSERT OR IGNORE on the unique key), `list_findings(filters, cursor)`, `get_rule_versions(rule_id)`.
Rules are never hard-deleted if findings reference them: custom rules are **soft-deleted** (`deleted_at`) and hidden.

## 5.4 Engine — `core/rules/engine.py`
`evaluate_rules(rules, events, now) -> list[Finding]` dispatches by kind (Phase 5: threshold only; kinds not yet implemented return an explicit `NotImplementedForKind` warning in the result, never silently skipped). `engine/` loads enabled rules each cycle, queries only the events inside the maximum window of any enabled rule (+ cooldown), evaluates, saves findings, and for each **new** finding emits a `rule_triggered` event (source `rules`, `severity` = tier severity, `severity_source="rule:<id>"`, `details={rule_id, rule_version, tier_label, group_key, observed, threshold, window_seconds, evidence_event_ids, mitre, points}`; description = the explanation). The event's deterministic hash makes re-runs idempotent.

## 5.5 Backtest — `core/rules/backtest.py` (pure) + storage wrapper
`backtest_rule(rule_definition, events, start, end) -> BacktestResult` evaluates an **unsaved or saved** definition against historical events and returns: findings (not persisted), counts per tier/severity, distinct groups affected, top 10 groups, a timeline histogram, up to 20 sample evidence events per finding, and "noise estimate" = findings per day. API wrapper limits range (≤ 30 days), event count (≤ 200 000; else error asking for a shorter range) and runs in a thread with a time limit. Used by `POST /api/rules/preview` and `POST /api/rules/{id}/backtest`.

## Worked example — user's request
Rule above, group `203.0.113.45`, events at 10:00:00 + every 20 s for 20 events (last at 10:06:20), then 30 more at 1 s spacing from 10:10:00:
- Tier 0 (≥5/10 min) satisfied at the 5th event (10:01:20) → finding **medium**.
- Tier 1 (≥20/10 min) satisfied at the 20th event (10:06:20) → **escalation** finding **high**.
- Tier 2 (≥50/60 s) is **not** satisfied by the first 20, and the later 30 events within 30 s give count 30 < 50 → no critical. Count < threshold boundaries tested at 49/50.
- A cooldown of 900 s means the later burst (10:10:00 onward) is part of the same episode: only escalations are reported, not another medium.

## Tests (minimum)
Validation: every rule above; each error path with message; warnings for dominated tiers; unknown keys; fixed-mode window rule. Evaluator: exact boundaries (count N−1 / N / N+1; window edge inclusive/exclusive: events exactly `window_seconds` apart are **not** in the same window — define and test); unsorted input; duplicate timestamps (ordering by id); multiple groups independent; missing group field; distinct_count; sliding vs fixed difference (events straddling a minute boundary: sliding satisfies, fixed does not); cooldown and escalation semantics; allowlisted exclusion; deterministic keys; evidence cap; explanation text; hypothesis: findings are invariant under input order and under duplicate event objects with distinct ids not exceeding counts. Storage: versions bump; reset; soft delete; unique findings; re-run idempotent; `rule_triggered` events deduplicated by hash. Backtest: counts, limits, noise estimate, unsaved definition, does not persist anything. Performance test: 200 000 synthetic events evaluate within a documented budget (record the measured time in `docs/DECISIONS.md`).

## Gate
Green suite; mypy strict on `core/rules/`; user's example scenario passes as a named test `test_user_example_tiers`.
