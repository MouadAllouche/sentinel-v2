# Phase 20 — Threat simulator and detection report

Skills: sentinel-testing-workflow, sentinel-safe-collection, sentinel-rules-engine, sentinel-correlation-incidents, sentinel-explainability, sentinel-security-hardening, sentinel-docs-writing.

## Goal
A **sandboxed** simulator that replays realistic attack and benign-activity scenarios through Sentinel's real pipeline and reports, for each scenario, what Sentinel detected, how it prioritised it, how fast, and what it missed. It answers: "how does Sentinel deal with real-life threats?" It must never touch the real system.

## Hard safety rules (tests must pin all of them)
1. **Synthetic only.** The simulator writes only inside its own workdir (default `sim_workdir/`, git-ignored). It generates synthetic `auth.log` / `dpkg.log` lines and a fake `etc/` tree there. It never writes to `/var/log`, `/etc`, home directories or any real monitored path, and refuses (with an error) any workdir that resolves outside the project folder or into a system directory.
2. **No real attacks.** It never opens network connections, never runs `ssh`, `sshpass`, `nmap` or any subprocess, never contacts another host. Network, listening-port and process evidence comes from **fake feed adapters** injected into the collectors, not from `psutil` on the real machine.
3. **No sudo, no privilege changes.** No `chmod`/`chown` outside the sandbox tree.
4. Uses a **separate database per scenario** plus one combined database for the dashboard (`sim_workdir/sim.db`). Never opens the real `sentinel.db`.
5. Deterministic: same `--seed` produces the same events, findings, incidents and report. Time is simulated with an injected clock; no real sleeping unless `--live`.
6. The real-traffic VM approach stays **documentation only** (`scripts/generate_attack_vm.md`); the simulator does not automate it.

## 20.1 Interface
`python cli.py simulate list` — print the scenario catalogue.
`python cli.py simulate run <scenario|all> [--seed N] [--format table|md|json] [--out DIR]` — run in simulated time (fast), write the report.
`python cli.py simulate dashboard [--seed N]` — build the combined "realistic week" database and session key file in the sandbox and print how to start the API and web against it.
`python cli.py simulate live [--speed X]` — append the combined scenario's events gradually to the sandbox log so the dashboard's live feed and SSE update (optional; stops cleanly on Ctrl+C).
`python cli.py simulate whatif <scenario> --rules FILE.json` — run a scenario with a modified rule set (exported from the dashboard) and show the outcome difference against the default rules. This demonstrates the user-defined rule engine.
Implementation lives in `scripts/simulator/` (package: `scenarios.py`, `generators.py`, `feeds.py`, `runner.py`, `evaluate.py`, `report.py`) with the CLI wiring in `cli.py`. No new dependencies.

## 20.2 Scenario model
Each scenario is a dataclass:
```
Scenario(id, title, description, mitre: [..], category: "attack" | "benign" | "evasion",
         build(rng, clock) -> SimulatedActivity,           # auth/dpkg lines, file mutations, feed records, with timestamps
         expectation: Expectation)
Expectation(should_detect: bool, rules_any_of: [...], min_severity, incident: "yes"|"no"|"either",
            max_false_positive_severity, note)
```
`SimulatedActivity` bundles: timestamped auth.log lines (rsyslog ISO format, identical to what the real collector parses), dpkg lines, sandbox file mutations (create/chmod/append inside the fake tree, applied at given simulated times), and fake-feed records (new connection, new listening port, new process) — all fed to the real collectors through their normal interfaces.

### Scenario catalogue (minimum)
| id | category | What happens | Expected |
|---|---|---|---|
| `ssh-bruteforce-single-ip` | attack | 60 failed logins from one IP over 10 min, mixed valid and invalid users | `ssh-bruteforce-by-ip`, reaching tier ≥20 (high) |
| `password-spraying` | attack | one IP tries 12 usernames, 2 attempts each, slowly | `ssh-password-spraying` |
| `distributed-bruteforce` | attack | 15 different IPs, 3 attempts each against `admin` | `ssh-distributed-single-user` |
| `credential-compromise-chain` | attack | failures → success → `sudo visudo` → change in `sudoers.d` | one incident, severity critical, score reasons list ≥4 rules |
| `scanner-preauth-flood` | attack | many pre-auth disconnects and invalid users from one scanner | `ssh-preauth-scanning` |
| `login-from-new-ip` | attack | user with 10 prior logins from 2 IPs logs in from a new public IP | `new-ip-login` |
| `backdoor-account` | attack | `useradd` then add to `sudo` group | `new-user-created`, `user-added-to-privileged-group` |
| `persistence-cron` | attack | new file in `etc/cron.d` | `persistence-change` |
| `persistence-ssh-key` | attack | new key appended to `authorized_keys` | drift event naming the key fingerprint, `persistence-change` |
| `config-tampering` | attack | `sshd_config` made world-writable | `world-writable-sensitive-file`, critical |
| `suspicious-process` | attack | fake process feed: binary running from `/tmp` | `suspicious-process` |
| `unexpected-listener` | attack | fake feed: new listener on `0.0.0.0:4444` | `new-listening-port-all-interfaces` |
| `recon-tool-install` | attack | `dpkg` line installing `nmap` | `recon-or-attack-tool-installed` |
| `failed-login-spike` | attack | 7 benign days then a 40-event spike in one hour | baseline anomaly with numeric explanation |
| `low-and-slow` | **evasion** | 1 failed login every 7 min for 24 h from one IP, staying under every threshold window | **expected: not detected** by threshold rules; the report must show it as a known blind spot, not a failure |
| `benign-admin-day` | **benign** | normal logins from a trusted IP, routine sudo, apt installs, two typo'd passwords | **no incident**, no finding above low |
| `benign-noisy-user` | **benign** | one user with 3 failed logins spread across a day, then success | no incident |
| `benign-allowlisted-monitor` | **benign** | a monitoring host with many failed logins that is on the allowlist | events stored and visible, **no alert or incident** (suppression visible in the report) |
| `mixed-realistic-week` | combined | 7 days of benign noise with 3 attacks hidden inside | used for the dashboard database |

Scenarios use documentation-reserved IPs (`203.0.113.0/24`, `198.51.100.0/24`, `192.0.2.0/24`) and invented usernames, never real addresses.

## 20.3 Runner
`run_scenario(scenario, seed)`:
1. Create a fresh sandbox DB and fake tree; `init_db`, seed defaults (real seeded rules, real severity defaults).
2. For multi-day scenarios, pre-load benign history so baselines can mature.
3. Advance a **simulated clock** in steps equal to the engine interval (60 s), at each step expose the activity that "happened" up to that moment to the real collectors, then call the real `run_cycle(now=clock)`. Record the simulated time of the first detection (first finding/incident that matches the expectation).
4. Collect results: findings (rule, tier, severity), incidents (id, severity, score, reasons), anomalies, drift events, notifications captured by a **fake notification sink** (a channel with `min_severity=high`; no real transport), and suppressed (allowlisted) counts.
5. Evaluate against the `Expectation`.

## 20.4 Evaluation and report (`evaluate.py`, `report.py`)
Per scenario: `detected` (bool), `matched_rules`, `highest_severity`, `incident_id`, `score`, `time_to_detect` (simulated seconds from the first malicious event to the first matching finding), `false_positives` (findings/incidents in benign scenarios above the allowed severity), `outcome`:
`TRUE_POSITIVE`, `FALSE_NEGATIVE` (should have detected, did not), `TRUE_NEGATIVE`, `FALSE_POSITIVE`, `KNOWN_BLIND_SPOT` (evasion scenario with `should_detect=False` and nothing fired), `UNEXPECTED_DETECTION` (evasion scenario that was detected, flagged as a good surprise worth investigating).
Aggregate: counts per outcome, detection rate on attack scenarios, false-positive count on benign scenarios, median time to detect, severity distribution, and a **per-MITRE-technique coverage table**.
Report formats: console table, `report.md` (human readable: summary, matrix, per-scenario detail with the explanation text Sentinel produced, blind spots section with why), `report.json`. Report wording rules: "detected N of M simulated scenarios", never "accuracy" or "protects against"; always include the line "Synthetic scenarios test rule behaviour, not real-world detection performance"; list what the simulator does **not** model (encrypted traffic, memory-only malware, kernel rootkits, zero-days, anything outside logs/connections/processes/files).

## 20.5 What-if
`whatif`: run the scenario twice, default rules vs the supplied rule file (validated by the real rule validator; invalid → clear error), and print a diff: findings gained/lost, severities changed, score change, time-to-detect change. Used to show e.g. that lowering the brute-force tier from 5 to 3 catches an additional low-volume scenario, and what extra false positives appear on the benign scenarios.

## 20.6 Documentation
`docs/SIMULATION.md`: scenario catalogue with MITRE tags and the expected rules, how to run each command, how to read the report, how to view a scenario in the dashboard (`simulate dashboard`, then the printed commands), how to add a scenario, the safety guarantees, and the limits above. Update `docs/DEMO.md`, `docs/LIMITATIONS.md`, `README.md` (one short section) and `docs/RULES.md` (what-if). The kit's `docs coverage` test must also assert every scenario id appears in `docs/SIMULATION.md`.

## 20.7 Tests (test-first)
- **One test per scenario** asserting its `Expectation` through the real pipeline (including the two evasion/blind-spot ones, which pin "not detected" so a future improvement shows up as a deliberate change).
- Benign scenarios: zero incidents, zero findings above the allowed severity, allowlisted evidence present and flagged.
- Determinism: same seed → byte-identical `report.json`; different seed → same outcomes.
- Safety: the simulator refuses workdirs outside the project or in system directories; a test patches `socket`, `subprocess`, `psutil` real calls and `open` for write to fail outside the sandbox and runs every scenario; the real `sentinel.db` is never opened; no file outside `sim_workdir/` changes (compare a directory hash before and after).
- Idempotence: running a scenario twice in the same sandbox does not duplicate events/incidents.
- Report: aggregate math (rates, medians, MITRE coverage) on a crafted result set; wording rules (the mandatory disclaimer, no "accuracy" string); markdown/JSON validity.
- What-if: diff correctness; invalid rule file rejected; default rules never mutated.
- Time-to-detect: for `ssh-bruteforce-single-ip`, equals the simulated gap to the 5th failure's cycle within one engine interval.
- CLI: `simulate list/run/whatif/dashboard` via `main(argv)` with exit codes.
- `simulate dashboard`: the produced DB opens through the real API in a `TestClient` login test (credentials from the generated key/credentials file), and the incident list shows the hidden attacks.
- Fixture hygiene: scenario inputs pass through the real parsers (`parse_auth_line`), not hand-built event dicts.

## 20.8 Gate
`make test`, `make lint`, `make web-test` green; `python cli.py simulate run all` finishes in under 3 minutes and prints the matrix; `report.md` generated; reviewer and security-auditor have no blockers; commit `phase-20: threat simulator and detection report`. Report the real matrix in your final message and list every `FALSE_NEGATIVE` and `FALSE_POSITIVE` honestly with a diagnosis of the cause (rule gap, threshold, correlation, or simulator realism), without tuning thresholds just to make the matrix green.
