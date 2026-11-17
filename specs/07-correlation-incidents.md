# Phase 7 — Correlation, incidents, timeline, workflow, MITRE

Skills: sentinel-correlation-incidents, sentinel-explainability, sentinel-sqlite-patterns, sentinel-testing-workflow.

## Goal
Turn events and rule findings into **incidents**: groups of related evidence with a chronological, explained timeline, an analyst workflow and indicative MITRE ATT&CK tags. Correlation is **inference**, never proof, and always shows why.

## 7.1 Correlation — `core/correlation.py` (pure)
Input: list of events (including `rule_triggered` events), settings (`window_minutes=15`, `max_incident_span_hours=24`, `ignore_ips`, `ignore_usernames_for_linking=["root"]` unless combined with another strong key), `now`. Output: `Link` objects and connected components.

Link kinds (each stores `relation_reason` in plain language and `link_strength`):
| Kind | Condition | Strength |
|---|---|---|
| `shared_ip` | same non-ignored `source_ip`, within window of each other | strong |
| `shared_username_auth` | same username on auth-type events (failed/successful/invalid/sudo/su), within window; `root` alone is **not** sufficient — needs another strong link in the component | strong |
| `rule_evidence` | a `rule_triggered` event and each event in its `details.evidence_event_ids` | strong |
| `same_group_key` | two `rule_triggered` events whose `group_key` shares a value (e.g. same `source_ip`) | strong |
| `follows_login_same_user` | a `sudo_command`/`su_command`/`process_started`/`network_connection` by the username of a `successful_login`, within window **after** the login | weak |
| `time_proximity_host` | host-level event (`config_drift`, `user_created`, `group_member_added`, `new_listening_port`, `package_installed`) within window **after** any event already in an incident component | weak |
| `shared_process` | same `process_name` + same username, within window | weak |

Reason text examples: `"Same source IP 203.0.113.45; 3m 12s after the previous event"`, `"Rule evidence: 'SSH brute force from one IP' (tier ≥20 in 10 min) matched this failed_login"`, `"Weak: config_drift occurred 4m after sudo_command by admin; no shared IP or user, time proximity only"`.

Components: union–find over time-sorted events; split a component when its span exceeds `max_incident_span_hours`; weak links may **extend** a component but cannot **create** one: a component must contain ≥1 **anchor** event — `failed_login`, `invalid_user`, `rule_triggered`, `config_drift` (any severity ≥ medium), `anomaly`, `suspicious_process`, `user_created`, `group_member_added`. Plain `network_connection`, `process_started`, `system_info`, lone `successful_login`, `package_*` never create incidents; they can join. Allowlisted-with-suppression events never create incidents and are excluded from components (they remain visible via the events explorer).

Determinism requirements: result independent of input order; a component's identity is the **earliest anchor event hash** (`correlation_key`).

## 7.2 Incidents — `core/incidents.py` (pure) + `storage` + `engine`
- `plan_incidents(events, existing_incidents, now) -> list[IncidentChange]` (pure): `Create`, `Extend`, `Merge(into, absorbed)`, `NoChange`. Existing incidents are matched by **event overlap**; a new component bridging two incidents merges them (the older keeps the id; the other gets `status="merged"`, `merged_into`); closed incidents are **re-opened as new incidents** if new matching evidence arrives after `reopen_after_hours` (default 6) — otherwise they are extended and moved to `open` with a status-history row.
- Title generator: `"Possible brute force from 203.0.113.45 targeting admin (followed by successful login)"`, based on the strongest rule findings (fallback `"Suspicious activity from <ip>"`).
- Summary: 2–4 sentences generated from facts only, with inferences marked: counts, first/last seen, rules triggered, config changes.
- Idempotent: running twice yields identical incidents; feeding events in any order yields identical incidents (property test).
- Migration `m005`: `incidents`, `incident_events`, `incident_notes`, `incident_status_history`.

## 7.3 Timeline — `core/timeline.py` (pure)
`build_timeline(incident, events, links, findings) -> list[TimelineEntry]` ordered by `(timestamp, id)`:
```
{ timestamp, event_id, event_type, severity, summary, kind: "observed" | "inferred",
  relation_to_previous: {reason, strength, link_kind} | null, rule_findings: [{rule_id, tier_label}], mitre: [...] }
```
- `observed` entries come straight from events; `inferred` entries represent Sentinel's statements ("Possible credential-guessing sequence: 6 failures then a success from the same IP") and cite their evidence ids.
- `explain_incident(...) -> {grouping: [...link reasons grouped by strength], rules: [...], caveats: [...]}`; caveats always include "Grouping is based on shared attributes and time proximity and is not proof of a single actor" and list weak links explicitly.

## 7.4 Workflow
Statuses: `open → investigating → resolved | false_positive | closed`, plus system-set `merged`. Allowed transitions enforced (resolved/closed can reopen to `investigating`). `POST status` requires a reason when moving to `false_positive` or `resolved`. Notes: append-only, with author and timestamp. Assignee: free-text username of an existing user. All writes audited and recorded in `incident_status_history`. Marking `false_positive` does **not** delete evidence; it stops notifications and (optionally, admin choice) offers to create an allowlist entry.

## 7.5 MITRE — `core/mitre.py`
Static table `{technique_id: {name, tactic, url}}` for IDs used by seeded rules (T1110, T1110.001, T1110.003, T1078, T1548.003, T1098, T1098.004, T1136.001, T1053.003, T1543.002, T1222.002, T1021.004, T1046, T1571, T1059, T1595). Incident `mitre_json` = union over contributing rules, sorted by tactic order. Always labelled "indicative mapping; verify at attack.mitre.org". Agent: double-check IDs and names against attack.mitre.org when network is allowed; otherwise note them as unverified in `docs/DECISIONS.md`.

## Worked example
Events (UTC): 10:00–10:04 six `failed_login` from `203.0.113.45` (user admin); rule finding `ssh-bruteforce-by-ip` medium at 10:01; `successful_login` admin from same IP at 10:07 (finding `success-after-failures` high); `sudo_command visudo` by admin 10:09 (finding `sensitive-sudo` high); `config_drift` on `/etc/sudoers` at 10:12; unrelated failed_login from `198.51.100.7` at 10:05.
Expected: **one** incident containing all `203.0.113.45` evidence plus drift (weak link: "time proximity after sudo by admin"), and a **separate** incident (or none, if below anchor/rule thresholds — define: a lone failed_login is an anchor, so a low incident exists only if `create_incident` of a finding applies; otherwise it stays an event) for `198.51.100.7`. Document the chosen behavior: **incidents are created only when at least one rule finding with `actions.create_incident=true` or an anchor of severity ≥ medium exists in the component**; lone low events do not create incidents.
Timeline: 10:00 first failed login (observed) … 10:07 success (observed) … inferred "possible credential guessing succeeded" … 10:12 drift (weak link flagged).

## Tests
Each link kind with reason text; strength labelling; window boundaries; root-only linking prohibited; ignore_ips; anchor requirement; weak links extend-not-create; allowlist exclusion; span cap split; determinism (hypothesis: shuffle input → identical plan); idempotence; late event extends; bridging merges (absorbed marked); reopen rule; title/summary generation; timeline ordering and kinds; caveats present; status transition matrix incl. invalid transitions; notes append-only; history rows; MITRE union and ordering; storage round trips; the full worked example as `test_incident_worked_example`.

## Gate
Green suite; mypy strict on `core/correlation.py`, `core/incidents.py`, `core/timeline.py`, `core/mitre.py`.
