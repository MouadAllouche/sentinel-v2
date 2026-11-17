---
name: sentinel-rules-engine
description: Design and invariants of Sentinel's user-defined rules engine - rule kinds, condition DSL, tiers and windows, evaluation semantics, cooldown and escalation, backtesting, versioning, seeding and reset. Load when touching rules, conditions, severity overrides, risk rules, baseline-metric rules, or anything that evaluates user-defined logic.
---

# Rules engine

## Kinds
`threshold` (group_by, aggregate count|distinct_count, tiers, sliding|fixed windows) · `sequence` (steps, correlate_on, within_seconds) · `new_value` (field per entity, learning window) · `field_match` (single event conditions) · `baseline_metric` (metric, z tiers, min_absolute, maturity) · `incident_meta` (conditions on incident aggregates).

## Tier = `{label, count, window_seconds, severity, points}`
User example: ≥5 in 10 min → medium; ≥20 in 10 min → high; ≥50 in 60 s → critical. Highest satisfied tier wins per group/episode; escalation to a higher tier creates a new finding; lower tiers never re-fire after a higher one in the same episode; cooldown suppresses repeats.

## Window semantics (be exact, test boundaries)
- Sliding: events in `(t − window, t]`; two events exactly `window` apart are **not** in the same window. Count ≥ threshold satisfies (N−1 no, N yes).
- Fixed: UTC-aligned buckets (minute/hour/day); tier windows must equal the alignment length.

## Purity and determinism
Evaluators: `evaluate(rule, events, now) -> list[Finding]` — no DB, clock or I/O. Output independent of input order. Finding unique key `(rule_id, group_key, tier_index, window_start)`. Evidence ids capped (500) but `observed` is the true count. Every finding carries a generated plain-language explanation.

## Condition DSL
`{field, op, value}` + `all|any|not` groups (depth ≤ 4). Ops: eq ne in not_in contains not_contains startswith endswith regex gt gte lt lte exists not_exists cidr_in cidr_not_in. Dotted paths into `details.*`/`enrichment.*`. Missing field → false. **Regex safety**: length ≤ 200, compile at validation, reject nested quantifiers, evaluate on ≤ 500 chars. Provide `describe(cond)` for UI text.

## Validation
Pydantic v2, `extra="forbid"`, path-aware errors `[{path,message}]`, plus non-fatal **warnings** (dominated tiers). Limits: ≤ 10 tiers, count 1–100 000, window 10 s–30 d, points 0–100, ≤ 500 list items, slug ids.

## Lifecycle
Rules stored as JSON with `version`; every update writes `rule_versions` and an audit row; built-ins keep `default_definition_json` for reset; custom rules soft-delete; built-ins can only be disabled. Seeding inserts missing only. Rule changes affect **future** evaluation; history is untouched unless the user runs an explicit re-apply.

## Backtest
`backtest_rule(definition, events, start, end)` evaluates unsaved or saved definitions on history without persisting; returns counts by tier/severity, groups, noise per day, samples. Enforce range ≤ 30 days and event cap with a clear error.

## Integration
Findings → `rule_findings` rows + a deterministic `rule_triggered` event (source `rules`, severity = tier severity, `severity_source="rule:<id>"`) so correlation, scoring and notifications use one path. Incident score = Σ distinct rules' highest-tier points (+ meta rules), capped 100; incident severity = max(score band, highest finding severity).
