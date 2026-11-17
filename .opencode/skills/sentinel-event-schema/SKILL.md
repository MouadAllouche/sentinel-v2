---
name: sentinel-event-schema
description: Canonical Sentinel event format, field meanings, event-type and source taxonomy, UTC timestamp rules, event hashing and dedup. Load before creating or changing collectors, the normalizer, validation, event storage, or any code that builds or reads event dicts.
---

# Sentinel event schema

## Fields
Required: `timestamp` (UTC ISO 8601 `+00:00`), `source`, `event_type`, `severity` (`low|medium|high|critical`), `description` (non-empty).
Optional (only when known): `username`, `source_ip`, `local_ip`, `destination_ip`, `destination_port` (int), `connection_status`, `process_id` (int), `process_name`, `user_permissions` (`{"before":[str],"after":[str]}`), `file_path`, `details` (dict), `enrichment` (dict), `severity_source`.

## IP fields — never mix
- `source_ip`: remote initiator (SSH client).  - `local_ip`: this host.  - `destination_ip/port`: remote end of outbound traffic.

## Taxonomy
event_type: failed_login, successful_login, invalid_user, preauth_disconnect, sudo_command, su_command, user_created, user_deleted, group_member_added, password_changed, permission_change, network_connection, new_listening_port, process_started, suspicious_process, package_installed, package_removed, config_drift, anomaly, rule_triggered, system_info.
source: auth_log, journald, dpkg, network, listening, process, filesystem, system, baseline, rules.

## Rules
- Build raw dicts in collectors → `normalize_event()` → enrichment → allowlist → severity resolution → save. Never hand-roll a stored event.
- Normalizer keeps only known fields, resolves aliases (user→username, ip→source_ip, level→severity, message→description, action→event_type, process→process_name, permissions→user_permissions) and event-type aliases; drops unknown fields.
- Timestamps: aware UTC when stored; naive input assumed server-local and converted; use `core/timeutil.py`; inject `now`; never call `datetime.now()` in logic.
- Hash: `sha256(json.dumps(event_minus_{severity,severity_source,enrichment}, sort_keys=True, separators=(",",":"), default=str))`. Severity changes must never create duplicates.
- Sensitive data: never store file contents, secrets, command **arguments** (store executable + arg count), or full cmdlines. `details` holds structured, non-sensitive facts only.
- Collectors set provisional `severity="low"`; the severity resolver (defaults → overrides) decides the real one.

## Example
```python
{"timestamp":"2026-11-15T10:30:15+00:00","source":"auth_log","event_type":"sudo_command","severity":"low",
 "description":"User alice executed a sudo command as root","username":"alice","process_name":"visudo",
 "details":{"target_user":"root","command_executable":"/usr/bin/visudo","command_args_count":1}}
```
