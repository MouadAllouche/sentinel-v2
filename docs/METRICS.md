# Sentinel simulator evaluation metrics

All numbers below come from measured runs recorded in `metrics.json`. No value is estimated or tuned.

## Methodology

- Total simulated scenarios: 27
- Attack: 21; benign: 3; evasion: 2; combined: 1
- Distinct MITRE techniques covered: 18
- Built-in rules: 25; exercised: 15 across 5 rule kinds (baseline_metric, field_match, new_value, sequence, threshold)
- Seeds run: 20 (1–20)
- Baseline comparison seed: 1

## Results

Scenario-level counts per seed, then mean/min/max across seeds:

| Metric | Mean | Min | Max |
|---|---|---|---|
| tp | 20.000 | 20 | 20 |
| fn | 2.000 | 2 | 2 |
| tn | 3.000 | 3 | 3 |
| fp | 0.000 | 0 | 0 |
| precision | 1.000 | 1.000 | 1.000 |
| recall | 0.909 | 0.909 | 0.909 |
| f1 | 0.952 | 0.952 | 0.952 |
| benign_fp_count | 0.000 | 0 | 0 |

Outcomes identical across seeds: True
False positives on benign scenarios (per seed): mean 0.000, min 0, max 0

Missed or false-positive scenarios (seed 1), with diagnosis:

- **slow-rotating-bruteforce** (FALSE_NEGATIVE): rule gap or threshold: no finding fired on stored events
- **valid-user-spray-hourly** (FALSE_NEGATIVE): rule gap or threshold: no finding fired on stored events

## Time to detect

Simulated seconds from the first malicious event to the first matching finding.

| Attack scenario | Detections | Median | Min | Max |
|---|---:|---:|---:|---:|
| ssh-bruteforce-single-ip | 20/20 | 40.000 | 40.000 | 40.000 |
| password-spraying | 20/20 | 480.000 | 480.000 | 480.000 |
| distributed-bruteforce | 20/20 | 80.000 | 80.000 | 80.000 |
| credential-compromise-chain | 20/20 | 480.000 | 480.000 | 480.000 |
| scanner-preauth-flood | 20/20 | 95.000 | 95.000 | 95.000 |
| login-from-new-ip | 20/20 | 0.000 | 0.000 | 0.000 |
| backdoor-account | 20/20 | 0.000 | 0.000 | 0.000 |
| persistence-cron | 20/20 | 0.000 | 0.000 | 0.000 |
| persistence-ssh-key | 20/20 | 0.000 | 0.000 | 0.000 |
| config-tampering | 20/20 | 0.000 | 0.000 | 0.000 |
| suspicious-process | 20/20 | 0.000 | 0.000 | 0.000 |
| unexpected-listener | 20/20 | 120.000 | 120.000 | 120.000 |
| recon-tool-install | 20/20 | 0.000 | 0.000 | 0.000 |
| failed-login-spike | 20/20 | 0.000 | 0.000 | 0.000 |
| slow-rotating-bruteforce | 0/20 | N/A | N/A | N/A |
| valid-user-spray-hourly | 0/20 | N/A | N/A | N/A |
| stolen-credential-systemd-persistence | 20/20 | 420.000 | 420.000 | 420.000 |
| shell-profile-preload-persistence | 20/20 | 0.000 | 0.000 | 0.000 |
| ssh-key-plus-cron-delay | 20/20 | 0.000 | 0.000 | 0.000 |
| dev-shm-staging | 20/20 | 0.000 | 0.000 | 0.000 |
| legit-admin-3am | 20/20 | 0.000 | 0.000 | 0.000 |

## Prioritisation

Final severity, risk score and contributing rule reasons at seed 1.

| Attack scenario | Severity | Score | Rule reasons |
|---|---|---:|---:|
| ssh-bruteforce-single-ip | high | 60 | 3 |
| password-spraying | high | 40 | 2 |
| distributed-bruteforce | high | 25 | 1 |
| credential-compromise-chain | critical | 80 | 5 |
| scanner-preauth-flood | high | 55 | 4 |
| login-from-new-ip | medium | 10 | 1 |
| backdoor-account | medium | 25 | 2 |
| persistence-cron | high | 25 | 1 |
| persistence-ssh-key | high | 55 | 2 |
| config-tampering | critical | 70 | 2 |
| suspicious-process | high | 20 | 1 |
| unexpected-listener | medium | 10 | 1 |
| recon-tool-install | medium | 10 | 1 |
| failed-login-spike | high | 30 | 2 |
| slow-rotating-bruteforce | low | 0 | 0 |
| valid-user-spray-hourly | low | 0 | 0 |
| stolen-credential-systemd-persistence | critical | 70 | 4 |
| shell-profile-preload-persistence | high | 55 | 2 |
| ssh-key-plus-cron-delay | high | 55 | 2 |
| dev-shm-staging | high | 20 | 1 |
| legit-admin-3am | medium | 25 | 2 |

## Comparison with a naive baseline

The naive baseline is a **simple reference rule set**, not a real product: one rule, "5 or more failed logins from one IP in 10 minutes → alert". Seed 1.

| Scenario | Category | Sentinel default | Naive baseline |
|---|---|---|---|
| ssh-bruteforce-single-ip | attack | detected | detected |
| password-spraying | attack | detected | detected |
| distributed-bruteforce | attack | detected | missed |
| credential-compromise-chain | attack | detected | missed |
| scanner-preauth-flood | attack | detected | detected |
| login-from-new-ip | attack | detected | missed |
| backdoor-account | attack | detected | missed |
| persistence-cron | attack | detected | missed |
| persistence-ssh-key | attack | detected | missed |
| config-tampering | attack | detected | missed |
| suspicious-process | attack | detected | missed |
| unexpected-listener | attack | detected | missed |
| recon-tool-install | attack | detected | missed |
| failed-login-spike | attack | detected | detected |
| low-and-slow | evasion | missed (known blind spot) | missed (known blind spot) |
| benign-admin-day | benign | not detected (expected) | not detected (expected) |
| benign-noisy-user | benign | not detected (expected) | not detected (expected) |
| benign-allowlisted-monitor | benign | not detected (expected) | not detected (expected) |
| mixed-realistic-week | combined | detected | detected |
| slow-rotating-bruteforce | attack | missed | missed |
| valid-user-spray-hourly | attack | missed | missed |
| stolen-credential-systemd-persistence | attack | detected | missed |
| shell-profile-preload-persistence | attack | detected | missed |
| ssh-key-plus-cron-delay | attack | detected | missed |
| dev-shm-staging | attack | detected | missed |
| legit-admin-3am | attack | detected | missed |
| blended-low-slow | evasion | missed (known blind spot) | missed (known blind spot) |

Totals — Sentinel default: detected 20, missed 2, false positives 0. Naive baseline: detected 5, missed 17, false positives 0.

## Performance

Machine: Linux-7.0.0-42-generic-x86_64-with-glibc2.39
Python: Python 3.12.3 (CPython)
CPU: x86_64, 8 logical CPUs, x86_64
Memory: 16479649792 bytes total (psutil.virtual_memory())

| Measurement | Value |
|---|---|
| ingestion_events_per_second | 20642.7 |
| ingestion_seconds_for_100k | 4.844 |
| rule_evaluation_200k_seconds | 1.123 |
| api_calls_per_endpoint | 100 |
| api_events_median_ms | 11.13 |
| api_events_p95_ms | 13.02 |
| api_incidents_median_ms | 8.44 |
| api_incidents_p95_ms | 9.23 |
| database_bytes_per_100k_events | 73129984 |
| events_stored_for_api_benchmark | 200000 |

## Limitations

- Synthetic scenarios test rule behaviour, not real-world detection performance.
- The simulator models logs, connections, processes and files only; it does not model encrypted traffic, memory-only malware, kernel rootkits, zero-days, or a real adversary.
- Two red-team scenarios are false negatives with pre-registered expectations; they are reported, not tuned away.
- Performance figures are for this machine and this SQLite database, not a capacity guarantee.

## Slide-ready numbers

- **27** — synthetic scenarios measured
- **20** — independent seeds run across every scenario
- **18** — distinct MITRE techniques covered
- **1.000** — mean precision across seeds
- **0.909** — mean recall across seeds
- **0.952** — mean F1 across seeds
- **0.000** — mean false positives on benign scenarios per seed
- **20** — scenarios detected by Sentinel defaults at the baseline seed
- **5** — scenarios detected by the one-rule naive reference at the baseline seed
- **20642.7** — measured ingestion rate on this machine
- **1.123** — measured rule evaluation time over 200,000 events
- **11.13** — median /api/events latency over 100 calls
- **8.44** — median /api/incidents latency over 100 calls
- **73129984** — SQLite database size per 100,000 events
