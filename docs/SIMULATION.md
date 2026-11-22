# Threat simulator (Phase 20)

The simulator replays **synthetic** attack and benign-activity scenarios through
Sentinel's real pipeline. It answers "how does Sentinel deal with these
situations?" — detected scenarios, how they were prioritised, how fast, and what
was missed. It never touches the monitored machine.

**Synthetic scenarios test rule behaviour, not real-world detection performance.**

## Safety guarantees

- Writes only inside `sim_workdir/` (git-ignored). A workdir outside the project,
  or inside a system directory, is refused.
- No real logs, sockets, SSH, nmap, subprocesses, sudo or privilege changes.
  Network, listener and process evidence comes from injected fake feed adapters.
- One SQLite database per scenario plus a combined `sim_workdir/sim.db` for the
  dashboard. The real `sentinel.db` is never opened.
- Time is simulated and seeded; `--seed N` reproduces the same report.

## Commands

```bash
python cli.py simulate list
python cli.py simulate run all --seed 7 --format table
python cli.py simulate run ssh-bruteforce-single-ip --format md --out sim_workdir/report
python cli.py simulate dashboard --seed 7
python cli.py simulate live --speed 1000 --steps 5
python cli.py simulate whatif low-and-slow --rules my-rules.json
```

`--format` accepts `table`, `md` or `json`. For `run`, `dashboard`, `whatif` and
`live`, `--out DIR` is both the report directory and the simulator workdir: the
scenario databases sit beside the report. It must resolve inside the project.

`simulate dashboard` prints the exact API/web
start commands and creates a mode-0600 session key. `simulate live` appends
synthetic lines gradually (bounded by `--steps`, paced by `--speed`; Ctrl+C stops
cleanly). If a dashboard database already exists in the workdir, it appends to
that dashboard's auth log, re-runs collection and publishes change rows so the
dashboard's SSE/live updates fire; without one it only appends to a standalone
sandbox log. `simulate whatif` runs a scenario with an
exported rule set and prints findings gained/lost, severity changes, score and
time-to-detect changes.

## Scenario catalogue

| id | Category | MITRE (indicative) | Expected rule / outcome |
|---|---|---|---|
| `ssh-bruteforce-single-ip` | attack | T1110, T1110.001 | `ssh-bruteforce-by-ip` tier ≥20 (high) |
| `password-spraying` | attack | T1110.003 | `ssh-password-spraying` |
| `distributed-bruteforce` | attack | T1110 | `ssh-distributed-single-user` |
| `credential-compromise-chain` | attack | T1078, T1548.003 | one incident, `sensitive-sudo`, `persistence-change` |
| `scanner-preauth-flood` | attack | T1046 | `ssh-preauth-scanning` |
| `login-from-new-ip` | attack | T1078 | `new-ip-login` |
| `backdoor-account` | attack | T1136.001, T1098 | `new-user-created`, `user-added-to-privileged-group` |
| `persistence-cron` | attack | T1053.003 | `persistence-change` |
| `persistence-ssh-key` | attack | T1098.004 | drift naming a SHA-256 fingerprint, `persistence-change` |
| `config-tampering` | attack | T1222.002 | `world-writable-sensitive-file` (critical) |
| `suspicious-process` | attack | T1059 | `suspicious-process` (fake process feed) |
| `unexpected-listener` | attack | T1049 | `new-listening-port-all-interfaces` (fake listener feed) |
| `recon-tool-install` | attack | T1592 | `recon-or-attack-tool-installed` |
| `failed-login-spike` | attack | T1110 | `baseline-failed-logins` with numeric explanation |
| `low-and-slow` | evasion | T1110 | **known blind spot** — no threshold fires by design |
| `benign-admin-day` | benign | T1078 | no incident, no finding above low |
| `benign-noisy-user` | benign | T1078 | no incident |
| `benign-allowlisted-monitor` | benign | T1078 | events stored and labelled suppressed, no alert |
| `mixed-realistic-week` | combined | T1110, T1078, T1053.003 | three hidden attacks in the dashboard DB |
| `slow-rotating-bruteforce` | attack | T1110 | 3 attempts per 10 min from a rotating pool of 40 IPs |
| `valid-user-spray-hourly` | attack | T1110.003 | valid usernames only, one attempt per user per hour |
| `stolen-credential-systemd-persistence` | attack | T1078, T1543.002 | stolen credential, quiet escalation, systemd service |
| `shell-profile-preload-persistence` | attack | T1546.004, T1574.006 | shell profile and `ld.so.preload` changes |
| `ssh-key-plus-cron-delay` | attack | T1098.004, T1053.003 | SSH key then cron job minutes apart |
| `dev-shm-staging` | attack | T1059, T1074.001 | process started from `/dev/shm` staging data |
| `legit-admin-3am` | attack | T1136.001 | legitimate-looking admin account created at 03:00 |
| `blended-low-slow` | evasion | T1110 | malicious events hidden among 20 benign-looking actions each |

All addresses come from the documentation-reserved ranges
`203.0.113.0/24`, `198.51.100.0/24` and `192.0.2.0/24`. Usernames are invented.

## Red-team addendum (seed 7)

Eight harder scenarios were written from attacker behaviour only, before consulting any seeded
rule or threshold. Outcomes: `slow-rotating-bruteforce` and `valid-user-spray-hourly` were
**FALSE_NEGATIVE** (36 rotating sources with at most 3 attempts per 10 minutes; 12 valid usernames
one per hour — both below minute-scale grouping windows); the six persistence/process/account
scenarios were TRUE_POSITIVE; `blended-low-slow` was a KNOWN_BLIND_SPOT as expected. The two false
negatives were **not** tuned away; their pre-registered expectations remain and the corresponding
tests are strict expected failures (`xfail(strict=True)`, reason "known detection gap, see D-113")
so a future fix turns them into deliberate failures. Diagnosis: threshold/window and rule gap, not
simulator realism — the events were generated and stored correctly. See `docs/DECISIONS.md` D-113.

Correction after D-115: with the candidate rules, `valid-user-spray-hourly` now forms **one**
incident containing all 12 failed logins and both rule triggers (previously two thin incidents),
because rule-evidence and shared-group-key links are no longer bounded by the 15-minute window.
All other scenarios keep their incident counts, severities, scores and detection times; see
`docs/DECISIONS.md` D-116.

### `blended-low-slow` — exact actions and why it is expected to be missed

The scenario runs three identical rounds, 30 simulated minutes apart:

- **Malicious actions (3 total):** one `failed_login` per round against the invented user `admin`,
  all from the documentation-reserved source IP `203.0.113.45`. Timestamps are round start,
  round start + 30 min and round start + 60 min. There is no successful login from that IP and no
  subsequent privileged action by the attacker, so the only evidence is three widely spaced
  failures from one source.
- **Benign filler (20 per round, 60 total):** 16 `successful_login` events for the invented user
  `alice` from the documentation-reserved IP `198.51.100.7`, plus 4 `sudo_command` events by
  `alice` running `/usr/bin/id` (routine administrative command). These use a different source IP
  and a different username from the malicious events; they are ordinary activity, not attacks.
- **Why `should_detect=False`:** each malicious event is separated from the next by 20 benign
  actions and 30 simulated minutes. No short-window threshold sees more than one failure, and the
  attacker shares no IP or username with the filler, so no correlation link exists. A monitor that
  only aggregates failures in short windows has no evidence to act on. This is an evasion case, not
  a failure of the simulator: the three failures are stored and visible in the events table.
- **Would a reasonable monitor catch any of it?** A monitor with a long (multi-hour) window for
  repeated failures from one source against one account, or one with external reputation data for
  the source address, could plausibly flag the three failures across the hour. Sentinel's default
  rule set does not do that, so the honest expectation stays `False`. The expectation was not
  changed to make the matrix greener.

## Reading the report

The console table and Markdown report show a matrix (`scenario`, `outcome`,
severity, matched rules, time to detect), aggregate counts, a per-MITRE
coverage table, per-scenario explanations from Sentinel itself, and a blind
spots section. Outcomes are `TRUE_POSITIVE`, `FALSE_NEGATIVE`, `TRUE_NEGATIVE`,
`FALSE_POSITIVE`, `KNOWN_BLIND_SPOT` and `UNEXPECTED_DETECTION`. A false negative
is reported honestly, with a diagnosis; thresholds are not tuned to make the
matrix green.

The report always includes the disclaimer above and states what is not
modelled: encrypted traffic, memory-only malware, kernel rootkits, zero-days,
and anything outside logs, connections, processes and files.

## Viewing a scenario in the dashboard

```bash
python cli.py simulate dashboard --seed 7
# then run the two printed commands and open http://127.0.0.1:3000
```

The combined database contains the hidden attacks from `mixed-realistic-week`.
The dashboard uses the same API and UI as a live deployment.

## Adding a scenario

Add a builder to `scripts/simulator/generators.py` returning a
`SimulatedActivity` (timestamped auth/dpkg lines, sandbox file mutations and
fake feed records). Register a `Scenario` with an `Expectation` in
`scripts/simulator/scenarios.py`, add a test asserting the expectation, and add
the id, MITRE tags and expected rule to the table above. Use reserved IPs and
invented usernames. Never add real hostnames, credentials or network targets.

## What-if

`simulate whatif <scenario> --rules FILE.json` takes a JSON list of exported
rule definitions, validates each with the real rule validator, and runs the
scenario twice (default rules vs supplied rules). The supplied rules are only
applied to a sandbox copy; the seeded defaults are never mutated.
