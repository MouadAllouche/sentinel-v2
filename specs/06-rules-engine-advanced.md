# Phase 6 — Rules engine: sequence, new-value, field-match, and seeded default rules

Skills: sentinel-rules-engine, sentinel-explainability, sentinel-testing-workflow.

## Goal
Complete the remaining detection kinds (except baseline-metric and incident-meta, which belong to Phases 8 and 10) and seed a complete, editable default rule set so Sentinel is useful out of the box.

## 6.1 Sequence rules — `core/rules/sequence.py`
Detect "A, then B (then C) for the same entity within a window".
```json
{
  "kind": "sequence",
  "id": "success-after-failures",
  "name": "Successful login after repeated failures",
  "correlate_on": ["source_ip"],               // entity keys; events must share ALL of these
  "within_seconds": 900,
  "steps": [
    { "name": "failures", "match": {"event_types": ["failed_login"]},     "min_count": 5, "window_seconds": 600 },
    { "name": "success",  "match": {"event_types": ["successful_login"]}, "min_count": 1 }
  ],
  "severity": "high", "points": 20, "cooldown_seconds": 900,
  "actions": {"create_incident": true, "notify": true, "tags": ["credential-access"]}, "mitre": ["T1110", "T1078"]
}
```
Semantics: for each entity (values of `correlate_on`), step *k+1* must occur **after** the satisfying moment of step *k* and within `within_seconds` of the first step's satisfying moment; step 1 may use its own `min_count`/`window_seconds` (reuse the threshold counting). Finding `window_start` = first evidence of step 1, `window_end` = the final step event; evidence = union of step evidence; unique key `(rule_id, group_key, 0, window_start)`. Steps ≤ 5. Optionally `correlate_on` may include `username` (e.g. "success for the same user from any IP") — tested both ways.

## 6.2 New-value rules — `core/rules/new_value.py`
"First time this user logs in from this IP" and similar.
```json
{ "kind": "new_value", "id": "new-ip-login", "name": "Login from a never-seen IP",
  "match": {"event_types": ["successful_login"]},
  "field": "source_ip", "per": "username",
  "learning_days": 30, "min_history_events": 5,
  "severity": "medium", "points": 10, "mitre": ["T1078"] }
```
Semantics: a finding fires when an event's `field` value was **not seen** in that `per` entity's history inside `learning_days` before the event, **and** the entity has ≥ `min_history_events` prior matching events (otherwise it is "learning", no finding, and the explanation of the rule's status says so). History is passed to the pure function as pre-aggregated sets so it stays pure (`evaluate_new_value(rule, events, history, now)`); storage supplies `history` by querying prior events. The same value in a later event is no longer new (test). Examples: `field=destination_ip, per=process_name` for outbound destinations; `field=source_ip, per=username`.

## 6.3 Field-match rules — `core/rules/field_match.py`
Single-event detections (sensitive sudo, new user, drift on persistence paths).
```json
{ "kind": "field_match", "id": "sensitive-sudo", "name": "Sudo of a sensitive command",
  "match": { "event_types": ["sudo_command"],
             "conditions": { "all": [ {"field": "process_name", "op": "in",
                              "value": ["visudo","passwd","useradd","usermod","userdel","chown","chmod","crontab"]} ] } },
  "severity": "high", "points": 20, "cooldown_seconds": 0, "group_by": ["username"],
  "mitre": ["T1548.003"] }
```
One finding per matching event (unique key uses the event id as the `window_start` surrogate = event timestamp + event id); `cooldown_seconds` > 0 collapses repeats per `group_by` key. Evidence = the matching event.

## 6.4 Reserved kinds (validated now, implemented later)
`baseline_metric` (Phase 8) and `incident_meta` (Phase 10) models and validators exist now, so the rule store, API and UI can hold them, but `evaluate_rules` returns an explicit "evaluated elsewhere" marker for them.

## 6.5 Seeded default rules — `core/rules/defaults.py`
All `builtin=true`, enabled unless noted, each with `default_definition_json` for reset. Points are design starting points and must be documented as uncalibrated.

| id | kind | summary | tiers / severity | points | MITRE |
|---|---|---|---|---|---|
| `ssh-bruteforce-by-ip` | threshold | failed_login+invalid_user per source_ip | ≥5/10m medium · ≥20/10m high · ≥50/60s critical | 15/30/45 | T1110.001 |
| `ssh-password-spraying` | threshold | failed_login per source_ip, **distinct usernames** | ≥5/10m high | 25 | T1110.003 |
| `ssh-distributed-single-user` | threshold | failed_login per username, **distinct source_ip** | ≥5/10m high | 25 | T1110 |
| `ssh-preauth-scanning` | threshold | preauth_disconnect per source_ip | ≥20/5m medium | 5 | T1046 |
| `success-after-failures` | sequence | see 6.1 | high | 20 | T1110, T1078 |
| `new-ip-login` | new_value | see 6.2 | medium | 10 | T1078 |
| `new-outbound-destination` | new_value | destination_ip per process_name, learning 14d, **disabled by default** (noisy) | low | 5 | — |
| `sensitive-sudo` | field_match | see 6.3 | high | 20 | T1548.003 |
| `new-user-created` | field_match | user_created | medium | 15 | T1136.001 |
| `user-added-to-privileged-group` | field_match | group_member_added with group in [sudo, adm, wheel, root] | high | 25 | T1098 |
| `sensitive-file-change` | field_match | config_drift, details.sensitivity in [high, critical] and details.changed_fields includes any of [sha256, owner, group, mode] | high | 30 | T1222.002 |
| `world-writable-sensitive-file` | field_match | config_drift with details.flags contains world_writable | critical | 40 | T1222.002 |
| `persistence-change` | field_match | config_drift where details.category in [cron, systemd, authorized_keys, ld_preload, shell_profile] | high | 25 | T1053.003, T1543.002, T1098.004 |
| `new-listening-port-all-interfaces` | field_match | new_listening_port with details.bind_scope = all_interfaces | medium | 10 | T1571 |
| `suspicious-process` | field_match | suspicious_process | high | 20 | T1059 |
| `recon-or-attack-tool-installed` | field_match | package_installed with package in [nmap, ncat, netcat, hydra, john, sqlmap, masscan] | medium | 10 | T1595 |

Baseline-metric and incident-meta defaults are seeded in Phases 8 and 10.

`seed_rules(db_path)` inserts only missing builtin rules (never overwrites user edits or deletions of custom rules); `reset_rule` / `reset_all_builtin_rules` restore defaults and are audited.

## Worked example — sequence
Events for `203.0.113.45`: 6 `failed_login` between 10:00 and 10:04, `successful_login` (user `admin`) at 10:07, then `sudo_command visudo` at 10:09 (user `admin`).
- `ssh-bruteforce-by-ip` → medium finding (tier 0).
- `success-after-failures` → one high finding, window 10:00–10:07, evidence = 6 failures + the success.
- `sensitive-sudo` → one high finding for the sudo event (different rule; incident scoring will count each rule once).

## Tests
Sequence: ordering enforced (success **before** failures never matches); step window; `within_seconds` boundary; multiple entities independent; `correlate_on` variants; three-step rule; cooldown; evidence union; idempotent unique key. New-value: learning state, first seen, repeat not new, history window expiry, per-entity isolation, pure-function signature. Field-match: each seeded rule fires/doesn't on fixture events; cooldown collapse; group_by. Seeding: idempotent; user edits survive re-seed; reset restores; disabled-by-default rule stays disabled. Cross-kind: the full worked example yields exactly the expected findings and `rule_triggered` events. Validation of reserved kinds. Property tests: evaluators never raise on arbitrary event lists (including missing fields).

## Gate
Green suite; seeded rule set validates; `docs/RULES.md` written describing every kind with the JSON examples above.
