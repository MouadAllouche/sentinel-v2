# Rules

Rules are validated JSON documents stored in SQLite. They are editable by an administrator,
versioned, resettable and evaluated by pure functions. **Points are uncalibrated design starting
points**, not statistically validated scores. Rule findings are evidence of a pattern, never proof
of an attack.

## Common fields

```json
{
  "id": "example-rule",
  "name": "Example rule",
  "description": "What this rule looks for",
  "kind": "threshold",
  "enabled": true,
  "match": {"event_types": ["failed_login"], "conditions": {"all": []}},
  "scope": {"exclude_allowlisted": true},
  "actions": {"create_incident": true, "notify": true, "tags": []},
  "mitre": ["T1110.001"]
}
```

`id` is a 3–64 character lowercase slug. `match.conditions` uses the shared condition DSL
(`all`/`any`/`not`, depth ≤ 4, operators `eq/ne/in/not_in/contains/not_contains/startswith/
endswith/regex/gt/gte/lt/lte/exists/not_exists/cidr_in/cidr_not_in`). Regex patterns are capped at
200 characters, compiled at validation, reject nested quantifiers and more than two unbounded
quantifiers (to prevent catastrophic backtracking), and evaluate on at most 500 characters. The
compiled-pattern cache is bounded to 128 entries. No DNS, GeoIP or network lookups occur in rule
evaluation.

## Kinds

### `threshold`

Groups events by `group_by`, counts (or distinct-counts) them in sliding `(t−window, t]` or
UTC-aligned fixed windows, and fires tiers. The highest satisfied tier by severity then points
wins per episode; escalation to a higher tier creates one additional finding. Cooldown suppresses
repeats. Evidence IDs are capped at 500 while `observed` keeps the true count.

```json
{
  "kind": "threshold",
  "group_by": ["source_ip"],
  "aggregate": {"type": "count"},
  "window_mode": "sliding",
  "fixed_alignment": null,
  "cooldown_seconds": 900,
  "tiers": [
    {"label": "Repeated failures", "count": 5, "window_seconds": 600, "severity": "medium", "points": 15},
    {"label": "Sustained attack", "count": 20, "window_seconds": 600, "severity": "high", "points": 30},
    {"label": "Burst", "count": 50, "window_seconds": 60, "severity": "critical", "points": 45}
  ]
}
```

Example: ≥5 failed logins in 10 minutes → medium; ≥20 in 10 minutes → high; ≥50 in 60 seconds →
critical. Events exactly `window_seconds` apart are **not** in the same window.

### `sequence`

Detects "A, then B (then C)" for the same entity. Step *k+1* must occur after step *k* and within
`within_seconds` of the first step's satisfying moment. Up to 5 steps.

```json
{
  "kind": "sequence",
  "correlate_on": ["source_ip"],
  "within_seconds": 900,
  "steps": [
    {"name": "failures", "match": {"event_types": ["failed_login"]}, "min_count": 5, "window_seconds": 600},
    {"name": "success", "match": {"event_types": ["successful_login"]}, "min_count": 1}
  ],
  "severity": "high", "points": 20, "cooldown_seconds": 900,
  "mitre": ["T1110", "T1078"]
}
```

### `new_value`

Fires when a field value has not been seen for an entity in the learning window and the entity has
enough prior history. The storage layer supplies pre-aggregated history, so evaluation is pure.
"Learning" is reported, not treated as normal.

```json
{
  "kind": "new_value",
  "field": "source_ip",
  "per": "username",
  "learning_days": 30,
  "min_history_events": 5,
  "severity": "medium", "points": 10, "mitre": ["T1078"]
}
```

### `field_match`

One finding per matching single event. `cooldown_seconds > 0` collapses repeats per `group_by`.
The finding identity uses the event id in `group_key` (`event=123`) with a real ISO `window_start`.

```json
{
  "kind": "field_match",
  "match": {"event_types": ["sudo_command"], "conditions": {"all": [
    {"field": "process_name", "op": "in", "value": ["visudo", "passwd", "useradd"]}
  ]}},
  "severity": "high", "points": 20, "cooldown_seconds": 0, "group_by": ["username"],
  "mitre": ["T1548.003"]
}
```

### `baseline_metric`

Compares the last completed hour against zero-filled hourly statistics from a configurable window.
A tier fires when `observed ≥ min_absolute` **and** `observed > mean + z × max(stddev, min_std)`.
An immature baseline produces `insufficient_baseline` and **no** anomaly event — never a fake
"all clear". Anomalies are unusual, not necessarily malicious.

```json
{
  "kind": "baseline_metric", "id": "baseline-failed-logins",
  "name": "Failed logins above normal",
  "metric": "failed_logins_per_hour", "subject": "global",
  "window_days": 7, "min_samples": 24, "min_history_hours": 24,
  "tiers": [
    {"label": "Elevated", "z": 3.0, "min_absolute": 5, "severity": "medium", "points": 10},
    {"label": "Extreme", "z": 6.0, "min_absolute": 20, "severity": "high", "points": 20}
  ],
  "min_std": 1.0, "cooldown_seconds": 3600,
  "actions": {"create_incident": false, "notify": true, "tags": []},
  "mitre": ["T1110"]
}
```

Seeded baseline rules: `baseline-failed-logins`, `baseline-new-connections-by-process`,
`baseline-distinct-destinations-by-process`, `baseline-successful-logins-by-user`,
`baseline-sudo-by-user`. `subject: "*"` evaluates every subject of the metric (top 50 by volume).

### Reserved kinds

`incident_meta` (Phase 10) is validated and stored now. The generic rule engine returns an explicit
`NotImplementedForKind` warning for it; it is never silently skipped. `baseline_metric` is evaluated
by the dedicated baseline cycle described above.

## Seeded rules

All seeded rules are built-in (`builtin=true`), resettable and enabled except where noted.

| id | kind | what it detects | points |
|---|---|---|---|
| `ssh-bruteforce-by-ip` | threshold | failed_login+invalid_user per source_ip, ≥5/10m medium · ≥20/10m high · ≥50/60s critical | 15/30/45 |
| `ssh-password-spraying` | threshold | distinct usernames per IP, ≥5/10m | 25 |
| `ssh-distributed-single-user` | threshold | distinct source IPs per username, ≥5/10m | 25 |
| `ssh-preauth-scanning` | threshold | preauth_disconnect per IP, ≥20/5m | 5 |
| `success-after-failures` | sequence | successful login after repeated failures, same IP | 20 |
| `new-ip-login` | new_value | first login from an IP for a user, 30-day learning | 10 |
| `new-outbound-destination` | new_value | first outbound destination per process, 14 days; disabled by default | 5 |
| `sensitive-sudo` | field_match | sudo of visudo/passwd/useradd/... | 20 |
| `new-user-created` | field_match | a local account was created | 15 |
| `user-added-to-privileged-group` | field_match | group_member_added for sudo/adm/wheel/root | 25 |
| `sensitive-file-change` | field_match | config_drift on sensitive files with security-relevant changes | 30 |
| `world-writable-sensitive-file` | field_match | config_drift gained world_writable | 40 |
| `persistence-change` | field_match | cron/systemd/authorized_keys/ld_preload/shell_profile change | 25 |
| `new-listening-port-all-interfaces` | field_match | new listener bound to all interfaces | 10 |
| `suspicious-process` | field_match | executable from a temporary location | 20 |
| `recon-or-attack-tool-installed` | field_match | nmap/ncat/hydra/... installed | 10 |
| `multiple-related-events` | incident_meta | distinct_event_types ≥ 3 | 10 |
| `credential-to-privilege-chain` | incident_meta | successful login + privileged activity | 15 |
| `anomaly-in-incident` | incident_meta | anomaly attached to incident | 10 |
| `drift-after-access` | incident_meta | successful login + persistence change | 20 |
| `baseline-failed-logins` | baseline_metric | failed logins/hour above the learned baseline | 10/20 |
| `baseline-new-connections-by-process` | baseline_metric | outbound connections/hour above baseline | 10/20 |
| `baseline-distinct-destinations-by-process` | baseline_metric | distinct destinations/hour above baseline | 5/10 |
| `baseline-successful-logins-by-user` | baseline_metric | successful logins/hour above baseline | 10 |
| `baseline-sudo-by-user` | baseline_metric | sudo commands/hour above baseline | 10 |

MITRE technique IDs are indicative mappings; verify them at attack.mitre.org.

## Editing rules

Use the rule builder in the UI (Phase 16) or the API: create, edit, disable, duplicate, import,
export, preview/backtest against history and reset to the seeded default. Editing a rule affects
future evaluations only; history is not rewritten by an edit. Every change is audited in
`audit_log` with actor, before/after and time. Backtesting currently supports **threshold** rules;
the other kinds return an empty result until their backtest support lands, and the API must report
that explicitly rather than presenting an empty result as "no findings".

# Building a rule in the dashboard

All steps are performed in the browser at `http://127.0.0.1:3000`. Only administrators can save
rules; viewers see a read-only view. The API remains authoritative: every value is validated again
on save.

## The user's example: 5 → medium, 20 → high, 10-minute window, grouped by source IP

1. Sign in as an administrator and open **Rules → New rule**.
2. **Basics**: set *Rule id* to `failed-logins-by-source-ip` and *Name* to `Failed logins by source IP`.
   The id is editable only when creating a rule.
3. **What to match**: check event type `failed_login` under Authentication. Optionally add conditions
   with *Add condition*; each row has a field, an operator and a value. The plain-language rendering
   under the builder updates as you type. Nested ALL/ANY/NOT groups are limited to depth 4.
4. **Group and count**: choose `source_ip` from *Group by* and `sliding` from *Window mode*. Sliding
   windows use `(t − window, t]`: two events exactly 10 minutes apart are **not** in the same window.
5. **Tiers**: the first tier already reads
   *"If ≥ 5 failed logins from the same source IP occur within 10 minutes → MEDIUM"*.
   Change its *Count* to `5`, *Window* to `10 minutes` and *Severity* to `medium`. Click **Add tier**,
   set the second tier to `20`, `10 minutes`, `high`, points `30`. Use ↑/↓ to reorder, remove with
   **Remove tier**. At most 10 tiers are allowed; server warnings such as dominated tiers appear
   below the cards.
6. **Actions**: keep *Exclude allowlisted events* on (the default). Decide whether to create an
   incident and whether to notify.
7. **Preview & backtest** (right rail): choose *last 7 days* (maximum 30) and wait for the debounced
   simulation. It shows total findings, severity counts and an approximate findings/day figure.
   *"No data in this range"* and *"Too much data — narrow the range"* are explicit states. Nothing is
   saved by a preview.
8. **Edit JSON** switches to a synchronised JSON view. It validates live; invalid JSON blocks the
   switch back with an explanation, so no state is lost.
9. **Save rule**: review the before/after diff dialog and confirm. A toast confirms the save and the
   version number increases. The rule appears in the list with the generated summary sentence:
   *"Failed logins grouped by source IP: ≥5 in 10 min → medium; ≥20 in 10 min → high"*.

## Other kinds

The kind selector is available on create only. `sequence` edits ordered steps with counts and a
correlation field; `new_value` uses a field, entity field and learning days; `field_match` uses the
condition builder; `baseline_metric` uses metric/subject and z-score tiers; `incident_meta` uses
conditions on incident aggregates. All kinds share validation, preview and diff-on-save.

## Version history and reset

Open an existing rule to see **Version history**. *Restore version N* creates a new version from the
older definition; history is never rewritten. Built-in rules offer **Reset** on the list and a reset
action in the editor. Import/Export JSON is available on the list; import errors are shown with the
exact document path.

## Safety

Regex conditions are limited to 200 characters, compiled at validation, reject nested quantifiers and
are evaluated against at most 500 characters. Viewers cannot bypass the server: the
builder's zod checks are advisory, and `POST /api/rules/validate` plus the save endpoint decide.
