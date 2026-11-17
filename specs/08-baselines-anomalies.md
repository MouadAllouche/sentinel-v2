# Phase 8 — Behavioral baselines, baseline-metric rules, anomalies

Skills: sentinel-rules-engine, sentinel-explainability, sentinel-sqlite-patterns, sentinel-testing-workflow.

## Goal
Learn what "normal" looks like from history using simple statistics, compare current behavior, and emit explained anomaly events. All parameters are user-editable through **baseline-metric rules**. No machine learning.

## 8.1 Metrics — `core/baseline.py` (pure)
Aggregate **hourly buckets, zero-filled** (an hour with no events counts as 0) over `window_days` (default 7) ending at the last **completed** hour (exclude the current partial hour). Events with `source="baseline"` or `rule_triggered` are **excluded** from baseline calculation (no feedback loops). Allowlist-suppressed events are excluded.

| Metric id | Subject | Counted events |
|---|---|---|
| `failed_logins_per_hour` | `global` | failed_login + invalid_user |
| `failed_logins_per_hour_by_ip` | source_ip (top 50 by volume) | failed_login |
| `successful_logins_per_hour` | username | successful_login |
| `new_connections_per_hour` | process_name | network_connection |
| `distinct_destinations_per_hour` | process_name | distinct destination_ip of network_connection |
| `sudo_commands_per_hour` | username | sudo_command |
| `known_login_ips` | username | set of source_ip of successful_login (set metric, feeds new-value reasoning) |

Output per metric/subject: `mean`, population `stddev`, `sample_count` (buckets), `max`, `p95`, window, plus `maturity`: **mature** only if `sample_count ≥ min_samples` (default 24) **and** the oldest relevant event (or oldest event of any kind in the DB) is ≥ `min_history_hours` (default 24) old; otherwise `immature` with the reason (`"only 6 hours of history; need 24"`).

Also support **hour-of-week profiles** (optional, default off): when enabled for a metric, compare against the same weekday-hour bucket history (needs ≥ 4 weeks; otherwise falls back to the global hourly baseline and says so).

## 8.2 Baseline-metric rules (rule kind `baseline_metric`)
```json
{ "kind": "baseline_metric", "id": "baseline-failed-logins", "name": "Failed logins above normal",
  "metric": "failed_logins_per_hour", "subject": "global",
  "window_days": 7, "min_samples": 24, "min_history_hours": 24,
  "tiers": [
    { "label": "Elevated", "z": 3.0,  "min_absolute": 5,  "severity": "medium", "points": 10 },
    { "label": "Extreme",  "z": 6.0,  "min_absolute": 20, "severity": "high",   "points": 20 }
  ],
  "min_std": 1.0, "cooldown_seconds": 3600, "actions": {"create_incident": false, "notify": true}, "mitre": ["T1110"] }
```
Seeded defaults (editable, resettable): `baseline-failed-logins` (above), `baseline-new-connections-by-process` (z 3/6, min_absolute 20, medium/high), `baseline-distinct-destinations-by-process` (z 3, min_absolute 10, low/medium), `baseline-successful-logins-by-user` (z 3, min_absolute 5, medium), `baseline-sudo-by-user` (z 3, min_absolute 5, medium). `subject: "*"` means evaluate every subject of the metric.
Validation: `z` 0.5–100 increasing across tiers; `min_absolute` ≥ 1; `min_std` ≥ 0.1.

## 8.3 Anomaly detection — `core/anomaly_detection.py` (pure)
For each enabled baseline-metric rule and subject, take the **last completed hour's value** `x` and the baseline:
- If baseline immature → result `insufficient_baseline` (returned for the UI, **no anomaly event**).
- `threshold = mean + z * max(stddev, min_std)`; a tier fires when `x ≥ min_absolute` **and** `x > threshold`; highest satisfied tier wins.
- Emit one `anomaly` event per (rule, subject, hour) with `source="baseline"`, `severity` = tier severity (`severity_source="rule:<id>"`), `details={metric, subject, observed, mean, stddev, threshold, z_observed, tier_label, window_start, window_end, sample_count, baseline_window_days, hour_start}`, and description like `"failed_logins_per_hour was 25 against a baseline mean of 2.0 (std 1.1, 168 hourly samples over 7 days), 20.9 standard deviations above normal"`.
- Deterministic and hash-deduplicated (one event per rule/subject/hour; re-running changes nothing). Also record a `rule_findings` row (so incidents/scoring/notifications treat it like any finding).
- Wording: an anomaly is **unusual**, not necessarily malicious; the explanation says so.

## 8.4 Storage, engine
Migration `m006`: `baselines`. `engine/` recomputes baselines every `analyze` cycle but **stores** one baseline row per metric/subject/day (not every cycle) to bound growth; `get_baseline_series(metric, subject, since)` returns hourly values + the baseline band (mean ± z·std) for charting. Cache computed baselines in memory per cycle.

## Worked example
Seven days of history for `failed_logins_per_hour` (global): hourly counts alternate 1–3 → mean 2.0, std 1.1 (168 samples). Current hour: 25. `25 ≥ 5` and `25 > 2.0 + 3·1.1 = 5.3` ⇒ Elevated; `25 ≥ 20` and `25 > 2.0 + 6·1.1 = 8.6` ⇒ Extreme (wins) → `high`, explanation "20.9 standard deviations above normal". Same data with only 6 hours of history → `insufficient_baseline`, no event. A value of 4 with `min_absolute=5` never fires even if z is huge (tiny-variance protection).

## Tests
Zero-filled buckets (gaps counted as 0); mean/std exact on crafted data; exclusion of baseline/rule events; completed-hour boundary (current hour excluded, DST/UTC safe); maturity combos (samples ok/history short and vice versa); z math; `min_std` floor; `min_absolute` floor; tier selection; immature → no event but reported; deterministic hash/one event per hour; re-run idempotent; subject `"*"` expansion and top-50 cap; hour-of-week fallback message; rule validation errors; seeded rules present/resettable; series endpoint data shape; performance with 30 days × 50 subjects; hypothesis: detection never raises on arbitrary counts.

## Gate
Green suite; mypy strict on `core/baseline.py`, `core/anomaly_detection.py`; `docs/RULES.md` updated for `baseline_metric`.
