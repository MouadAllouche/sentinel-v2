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
| backdoor-account | 20/20 | 0.000 | 0.000 | 0.000 |
| config-tampering | 20/20 | 0.000 | 0.000 | 0.000 |
| credential-compromise-chain | 20/20 | 480.000 | 480.000 | 480.000 |
| dev-shm-staging | 20/20 | 0.000 | 0.000 | 0.000 |
| distributed-bruteforce | 20/20 | 80.000 | 80.000 | 80.000 |
| failed-login-spike | 20/20 | 0.000 | 0.000 | 0.000 |
| legit-admin-3am | 20/20 | 0.000 | 0.000 | 0.000 |
| login-from-new-ip | 20/20 | 0.000 | 0.000 | 0.000 |
| password-spraying | 20/20 | 480.000 | 480.000 | 480.000 |
| persistence-cron | 20/20 | 0.000 | 0.000 | 0.000 |
| persistence-ssh-key | 20/20 | 0.000 | 0.000 | 0.000 |
| recon-tool-install | 20/20 | 0.000 | 0.000 | 0.000 |
| scanner-preauth-flood | 20/20 | 95.000 | 95.000 | 95.000 |
| shell-profile-preload-persistence | 20/20 | 0.000 | 0.000 | 0.000 |
| slow-rotating-bruteforce | 0/20 | N/A | N/A | N/A |
| ssh-bruteforce-single-ip | 20/20 | 40.000 | 40.000 | 40.000 |
| ssh-key-plus-cron-delay | 20/20 | 0.000 | 0.000 | 0.000 |
| stolen-credential-systemd-persistence | 20/20 | 420.000 | 420.000 | 420.000 |
| suspicious-process | 20/20 | 0.000 | 0.000 | 0.000 |
| unexpected-listener | 20/20 | 120.000 | 120.000 | 120.000 |
| valid-user-spray-hourly | 0/20 | N/A | N/A | N/A |

## Prioritisation

Final severity, risk score and contributing rule reasons at seed 1.

| Attack scenario | Severity | Score | Rule reasons |
|---|---|---:|---:|
| backdoor-account | medium | 25 | 2 |
| config-tampering | critical | 70 | 2 |
| credential-compromise-chain | critical | 80 | 5 |
| dev-shm-staging | high | 20 | 1 |
| distributed-bruteforce | high | 25 | 1 |
| failed-login-spike | high | 30 | 2 |
| legit-admin-3am | medium | 25 | 2 |
| login-from-new-ip | medium | 10 | 1 |
| password-spraying | high | 40 | 2 |
| persistence-cron | high | 25 | 1 |
| persistence-ssh-key | high | 55 | 2 |
| recon-tool-install | medium | 10 | 1 |
| scanner-preauth-flood | high | 55 | 4 |
| shell-profile-preload-persistence | high | 55 | 2 |
| slow-rotating-bruteforce | low | 0 | 0 |
| ssh-bruteforce-single-ip | high | 60 | 3 |
| ssh-key-plus-cron-delay | high | 55 | 2 |
| stolen-credential-systemd-persistence | critical | 70 | 4 |
| suspicious-process | high | 20 | 1 |
| unexpected-listener | medium | 10 | 1 |
| valid-user-spray-hourly | low | 0 | 0 |

## Comparison with a naive baseline

The naive baseline is a **simple reference rule set**, not a real product: one rule, "5 or more failed logins from one IP in 10 minutes → alert". Seed 1.

| Scenario | Category | Sentinel default | Naive baseline |
|---|---|---|---|
| backdoor-account | attack | detected | missed |
| benign-admin-day | benign | not detected (expected) | not detected (expected) |
| benign-allowlisted-monitor | benign | not detected (expected) | not detected (expected) |
| benign-noisy-user | benign | not detected (expected) | not detected (expected) |
| blended-low-slow | evasion | missed (known blind spot) | missed (known blind spot) |
| config-tampering | attack | detected | missed |
| credential-compromise-chain | attack | detected | missed |
| dev-shm-staging | attack | detected | missed |
| distributed-bruteforce | attack | detected | missed |
| failed-login-spike | attack | detected | detected |
| legit-admin-3am | attack | detected | missed |
| login-from-new-ip | attack | detected | missed |
| low-and-slow | evasion | missed (known blind spot) | missed (known blind spot) |
| mixed-realistic-week | combined | detected | detected |
| password-spraying | attack | detected | detected |
| persistence-cron | attack | detected | missed |
| persistence-ssh-key | attack | detected | missed |
| recon-tool-install | attack | detected | missed |
| scanner-preauth-flood | attack | detected | detected |
| shell-profile-preload-persistence | attack | detected | missed |
| slow-rotating-bruteforce | attack | missed | missed |
| ssh-bruteforce-single-ip | attack | detected | detected |
| ssh-key-plus-cron-delay | attack | detected | missed |
| stolen-credential-systemd-persistence | attack | detected | missed |
| suspicious-process | attack | detected | missed |
| unexpected-listener | attack | detected | missed |
| valid-user-spray-hourly | attack | missed | missed |

Totals — Sentinel default: detected 20, missed 2, false positives 0. Naive baseline: detected 5, missed 17, false positives 0.

## Performance

Machine: Linux-7.0.0-42-generic-x86_64-with-glibc2.39
Python: Python 3.12.3 (CPython)
CPU: x86_64, 8 logical CPUs, x86_64
Memory: 16479649792 bytes total (psutil.virtual_memory())

| Measurement | Value |
|---|---|
| api_calls_per_endpoint | 100 |
| api_events_median_ms | 26.45 |
| api_events_p95_ms | 30.92 |
| api_incidents_median_ms | 18.7 |
| api_incidents_p95_ms | 22.48 |
| database_bytes_per_100k_events | 73129984 |
| events_stored_for_api_benchmark | 200000 |
| ingestion_events_per_second | 13474.7 |
| ingestion_seconds_for_100k | 6.589 |
| rule_evaluation_200k_seconds | 2.067 |

## Clean benchmark conditions (5 interleaved runs per commit)

Date: 2026-11-22T17:19:14.660289+00:00. Measurements: 43ce0d7 (including correlation fix) vs a21b707 (last commit before correlation fix), alternating order so both saw the same conditions.

Machine: Linux-7.0.0-42-generic-x86_64-with-glibc2.39; x86_64, 8 logical CPUs, x86_64; 16479649792 bytes total (psutil.virtual_memory()); Python 3.12.3 (CPython).

No project tests, servers, builds or browsers running; persistent desktop services n8n (PIDs 3087, 3303) and chrome_crashpad handlers were present.

Load average before each run (1-minute): current 1.81, 2.23, 2.17, 3.18, 3.08; pre-fix 2.13, 2.17, 2.28, 2.53, 2.92.

| Metric | Current median | Current min–max | Pre-fix median | Pre-fix min–max |
|---|---:|---:|---:|---:|
| api_events_median_ms | 26.45 | 10.54–38.95 | 32.42 | 10.49–45.84 |
| api_events_p95_ms | 30.92 | 13.03–55.68 | 50.88 | 12.78–58.11 |
| api_incidents_median_ms | 18.7 | 7.99–20.36 | 22.91 | 8.46–39.52 |
| api_incidents_p95_ms | 22.48 | 10.08–25.03 | 27.73 | 11.79–46.66 |
| database_bytes_per_100k_events | 73129984 | 73129984–73129984 | 73129984 | 73129984–73129984 |
| ingestion_events_per_second | 13474.7 | 9415.7–29138.3 | 13575.4 | 10555.6–20842.5 |
| rule_evaluation_200k_seconds | 2.067 | 1.032–2.742 | 2.186 | 1.464–2.777 |

All between-variant median differences are smaller than the run-to-run spread within each variant; no regression or improvement can be claimed. DB size per 100k events is identical in every run.
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
- **13474.7** — measured ingestion rate on this machine (median of 5 interleaved runs)
- **2.067** — measured rule evaluation time over 200,000 events (median of 5 runs)
- **26.45** — median /api/events latency over 100 calls (median of 5 benchmark runs)
- **18.7** — median /api/incidents latency over 100 calls (median of 5 benchmark runs)
- **73129984** — SQLite database size per 100,000 events (identical in all 10 runs)
