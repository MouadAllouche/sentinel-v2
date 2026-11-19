# Risk rules and scoring

This document is generated from the seeded rule set in `core/rules/defaults.py`.
All point values are **uncalibrated design starting points**, editable by an administrator.
Each score is explained with the rules that fired, their tiers and their evidence. No rule is
counted twice in an incident.

## Scoring model

- Each event's own score is its event-type default; it is informational and is **not** summed into
  incident scores.
- An incident's raw score is the sum of the **highest tier of each distinct rule** that contributed
  a finding, plus any matching `incident_meta` rules. The score is capped at 100 (`capped=true`).
- Severity is `max(score band, highest fired-finding severity)`. Default bands are 0–19 low,
  20–39 medium, 40–69 high, 70–100 critical; the bands are editable in
  `app_settings["risk.severity_thresholds"]` and must be strictly increasing.
- Optional recency decay (`risk.recency_decay`) multiplies each contribution by
  `0.5 ** (age_hours / half_life)`, default off with a 72-hour half-life. Findings older than
  seven half-lives drop the incident to `low` unless it is open and a rule floor applies. An open
  incident keeps its rule floor because it is still under investigation; a closed critical finding
  never decays below `medium` because a severity the administrator already saw should not silently
  disappear from historical reporting. These are conservative, explainable choices, not statistics.
- If more than half the links are time-proximity only, a caveat reason is stored without changing
  the score.
- Reasons are stored in `risk_assessments.reasons_json` and rendered by `explain_score`.

## Seeded rules

| id | kind | points |
|---|---|---|
| `ssh-bruteforce-by-ip` | threshold | 15 / 30 / 45 |
| `ssh-password-spraying` | threshold | 25 |
| `ssh-distributed-single-user` | threshold | 25 |
| `ssh-preauth-scanning` | threshold | 5 |
| `success-after-failures` | sequence | 20 |
| `new-ip-login` | new_value | 10 |
| `new-outbound-destination` | new_value | 5 (disabled by default) |
| `sensitive-sudo` | field_match | 20 |
| `new-user-created` | field_match | 15 |
| `user-added-to-privileged-group` | field_match | 25 |
| `sensitive-file-change` | field_match | 30 |
| `world-writable-sensitive-file` | field_match | 40 |
| `persistence-change` | field_match | 25 |
| `new-listening-port-all-interfaces` | field_match | 10 |
| `suspicious-process` | field_match | 20 |
| `recon-or-attack-tool-installed` | field_match | 10 |
| `baseline-failed-logins` | baseline_metric | 10 / 20 |
| `baseline-new-connections-by-process` | baseline_metric | 10 / 20 |
| `baseline-distinct-destinations-by-process` | baseline_metric | 5 / 10 |
| `baseline-successful-logins-by-user` | baseline_metric | 10 |
| `baseline-sudo-by-user` | baseline_metric | 10 |
| `multiple-related-events` | incident_meta | 10 |
| `credential-to-privilege-chain` | incident_meta | 15 |
| `anomaly-in-incident` | incident_meta | 10 |
| `drift-after-access` | incident_meta | 20 |

## Standard example

`ssh-bruteforce-by-ip` (15), `success-after-failures` (20), `sensitive-sudo` (20),
`world-writable-sensitive-file` (40) and `sensitive-file-change` (30), plus meta rules
`multiple-related-events` (10), `credential-to-privilege-chain` (15) and `drift-after-access` (20),
give `raw_score = 170`, `score = 100` (capped) and severity `critical` from both the score band and
the rule floor. Disabling one rule lowers the raw score but leaves the incident critical; scores
and reasons are recomputed and stored on every analyze cycle.
