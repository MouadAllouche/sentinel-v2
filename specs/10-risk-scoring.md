# Phase 10 — Explainable risk scoring (incident-meta rules, scoring, recency decay)

Skills: sentinel-rules-engine, sentinel-explainability, sentinel-correlation-incidents, sentinel-testing-workflow.

## Goal
One transparent engine drives both alerts and scores. Every score is the sum of **distinct rules that fired** (highest tier per rule), with stored reasons and evidence. Nothing is double-counted, everything is editable by the admin, and thresholds are documented as uncalibrated starting points.

## 10.1 Event-level scores
Each event's score = `points` of its event type default (Phase 4) unless a severity override carries explicit `points`. Event scores are informational (explorer, event drawer) and are **not** added into incident scores. Reasons: `[{source:"event_type_default", points, explanation}]`.

## 10.2 Incident scoring — `core/risk_scoring.py` (pure)
`score_incident(incident, events, findings, meta_rules, thresholds, now, decay=None) -> RiskAssessment`

1. Collect the **rule findings** attached to the incident (via evidence overlap). Group by `rule_id`; for each rule keep only its **highest tier** (by severity then points). Each rule contributes **once**, regardless of how many findings or groups matched.
2. Evaluate **incident-meta rules** (rule kind `incident_meta`) on the incident aggregate.
3. `raw_score = Σ rule points` (distinct rules) ; `score = min(100, raw_score)`; keep `raw_score` and flag `capped`.
4. **Severity**: `score_severity(score, thresholds)` (defaults 0–19 low, 20–39 medium, 40–69 high, 70–100 critical; editable in `app_settings` key `risk.severity_thresholds`, validated: strictly increasing, 1–100) and `rule_floor = max(severity of fired findings)`; final severity = `max(score_severity, rule_floor)`; the reasons say which one decided (`"severity high from rule 'ssh-bruteforce-by-ip' tier 'Sustained attack' (floor)"`).
5. Reasons list (stored in `risk_assessments.reasons_json`): `[{rule_id, rule_name, tier_label, points, severity, explanation, evidence_event_ids, kind: "rule"|"meta"}]` plus summary entries: `{kind:"summary", raw_score, score, capped, severity_basis}`.

### Incident-meta rules (kind `incident_meta`)
```json
{ "kind": "incident_meta", "id": "multiple-related-events", "name": "Several distinct kinds of suspicious evidence",
  "conditions": [ {"metric": "distinct_event_types", "op": "gte", "value": 3} ],
  "severity": "medium", "points": 10 }
```
Metrics available: `distinct_event_types`, `distinct_rules_fired`, `event_count`, `has_event_type:<type>` (bool), `has_strong_links_only` (bool), `span_minutes`, `weak_link_ratio`, `contains_privileged_activity` (sudo/su/user_created/group_member_added), `contains_persistence_change`. Ops: `gte,lte,eq,ne,gt,lt`. All conditions must hold (AND); ≤ 5 conditions.
Seeded defaults (editable/resettable):
| id | condition | pts | severity |
|---|---|---|---|
| `multiple-related-events` | distinct_event_types ≥ 3 | 10 | medium |
| `credential-to-privilege-chain` | has_event_type:successful_login AND contains_privileged_activity | 15 | high |
| `anomaly-in-incident` | has_event_type:anomaly | 10 | medium |
| `drift-after-access` | has_event_type:successful_login AND contains_persistence_change | 20 | high |

Weak-evidence guard: if `weak_link_ratio > 0.5`, add a reason `"Many links are time-proximity only; treat the grouping with caution"` (no points change; it is a caveat).

## 10.3 Recency decay (optional, default **off**)
`risk.recency_decay = {enabled: false, half_life_hours: 72}`. When enabled, each rule's contribution is multiplied by `0.5 ** (age_hours / half_life)` where age is `now − finding.window_end`; the stored reasons show original and decayed points; incidents with all findings older than `7 × half_life` drop to `low` unless `status` is open and a rule floor applies (floor never decays below `medium` for critical findings — document the rationale). Pure and deterministic given `now`.

## 10.4 Persistence and propagation
Migration `m008`: `risk_assessments` (+ `app_settings` keys). `upsert_risk_assessment(target_type, target_id, ...)` replaces on recompute (idempotent); `incidents.risk_score` and `incidents.severity` updated in the same transaction; a **severity change** emits an internal change record used by notifications (Phase 11) and SSE (Phase 12). `explain_score(target_type, target_id) -> list[str]` returns the human-readable bullet list the UI shows: `"+15 Repeated failures — 6 failed logins from 203.0.113.45 within 10 min (rule ssh-bruteforce-by-ip, tier ≥5/10m)"`.

## Worked example (the standard scenario)
Fired in the incident: `ssh-bruteforce-by-ip` tier 0 (15), `success-after-failures` (20), `sensitive-sudo` (20), `world-writable-sensitive-file` (40) + `sensitive-file-change` (30), plus meta `multiple-related-events` (10), `credential-to-privilege-chain` (15), `drift-after-access` (20).
`raw_score = 15+20+20+40+30+10+15+20 = 170 → score 100 (capped)`, severity **critical**, reasons list shows each rule once. If the world-writable rule were disabled by the user: `130 → 100`, still critical; if also `sensitive-file-change` disabled: `100`. If only the brute-force rule fired with tier 1 (30) after the user changed its points to 50: score 50 → `high`; floor from the tier severity `high` agrees.
Boundary tests: 19→low, 20→medium, 39→medium, 40→high, 69→high, 70→critical.

## Tests
One rule fires many times → counted once; highest tier selected; no double counting between a rule and a meta rule on the same evidence (each rule id once); cap at 100 with `capped` flag; thresholds editable and validated (non-increasing rejected); rule-floor severity; reasons contain evidence ids and match the rules that fired (property test: sum of reason points == raw_score); meta metrics each; weak-link caveat; disabled rule excluded; custom user rule contributes; recompute idempotent; decay on/off, half-life math, floors; event-level scores; severity-change record emitted once; storage upsert; the full worked example as `test_risk_worked_example`.

## Gate
Green suite; mypy strict on `core/risk_scoring.py`; `docs/RISK_RULES.md` generated from the seeded rules (a test asserts the doc lists every seeded rule id).
