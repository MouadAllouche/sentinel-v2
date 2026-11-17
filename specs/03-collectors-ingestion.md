# Phase 3 — Collectors and ingestion

Skills: sentinel-safe-collection, sentinel-event-schema, sentinel-sqlite-patterns, sentinel-testing-workflow.

## Goal
Every evidence source becomes normalized events in SQLite, incrementally, idempotently, safely, with per-item error handling and visible health.

## Shared contract
```python
@dataclass
class CollectionResult:
    events: list[dict]          # raw-ish dicts; ingestion normalizes
    warnings: list[str]
    state: dict | None          # new collector state to persist AFTER events are saved
```
Collectors never raise for expected conditions (`PermissionError`, `FileNotFoundError`, `psutil.AccessDenied/NoSuchProcess/ZombieProcess`, malformed lines). They return a warning and continue. They never write to the system. Time-dependent behavior accepts `now`.

## Collectors

### `collectors/logs.py` — auth.log (rsyslog)
Keep these exact patterns and extend:
```python
FAILED_LOGIN      = r"Failed password for (?:invalid user )?(\S+) from (\S+)"
SUCCESSFUL_LOGIN  = r"Accepted (?:password|publickey|keyboard-interactive/pam) for (\S+) from (\S+)"
INVALID_USER      = r"Invalid user (\S+) from (\S+)"
PREAUTH_DISCONNECT= r"Connection closed by (?:authenticating|invalid) user (\S+) (\S+) port \d+ \[preauth\]"
SUDO_COMMAND      = r"sudo:\s+(\S+)\s+:.*?USER=(\S+)\s*;\s*COMMAND=(.+)$"
SU_COMMAND        = r"su(?:\[\d+\])?:\s+\(to (\S+)\) (\S+) on"
USER_CREATED      = r"new user: name=(\S+),"
USER_DELETED      = r"delete user '(\S+)'"
GROUP_MEMBER_ADD  = r"add '(\S+)' to (?:shadow )?group '(\S+)'"
PASSWORD_CHANGED  = r"password changed for (\S+)"
```
Mapping and default severities are **resolved later** by `core/severity.py`; collectors set a provisional `severity="low"`. Event fields: failed login `username, source_ip`; sudo `username` (the invoker), `process_name` = first token of the command (basename), `details={"target_user", "command_executable", "command_args_count"}` — **never store the argument string** (may contain secrets; store only executable and count); su `username` (invoker), `details.target_user`; user_created/user_deleted `details.account`; group_member_add `details={"account","group"}`; password_changed `details.account`.
- `extract_timestamp(line, year=None, now=None)`: ISO 8601 prefix, else syslog `Mon dd HH:MM:SS` with inferred year (current year; if the result is >1 day in the future use previous year).
- `parse_auth_line(line, year=None, now=None) -> dict | None`.
- `collect_auth_events(path, state, now=None) -> CollectionResult` incremental: state `{inode, offset}` under key `auth_log:<path>`; start at 0 first run; reset on inode change or file shrink; consume only complete lines; decode with `errors="replace"`; cap per-line length 4096 (skip longer with a warning); permission error → warning.
- An "Invalid user" line and the "Failed password for invalid user" line for the same attempt both parse (both are evidence; correlation tolerates duplicates).

### `collectors/journald.py`
Alternative/additional auth source when `/var/log/auth.log` is absent. Runs `journalctl` with an **argument list** (never a shell), `--since <cursor/time>`, `--output=json`, `-u <unit>`, `--no-pager`, timeout 20s. Persist the journal `__CURSOR__` as state. Feed `MESSAGE` through the same `parse_auth_line` patterns. Missing binary/permission → warning. Config: `collectors.auth_source = "auth_log" | "journald" | "both"`; with `both`, rely on event-hash dedup to avoid duplicates (timestamps must normalise identically — add a test).

### `collectors/dpkg.py`
Parse `/var/log/dpkg.log` lines `YYYY-MM-DD HH:MM:SS install|remove|purge <pkg> ...` into `package_installed` / `package_removed` (`details={"package","version"}`), incremental with offset state like the auth log.

### `collectors/network.py`
`psutil.net_connections(kind="inet")`; skip connections without `raddr` and `LISTEN`. Event: `source="network"`, `event_type="network_connection"`, `local_ip`, `destination_ip`, `destination_port`, `connection_status`, `process_id`, `process_name`, `username`, description `"Network connection detected"`. `get_process_details(pid) -> (name, username)` returning `(None, None)` for `None`/`NoSuchProcess`/`AccessDenied`/`ZombieProcess`. **State diff**: remember `(local_ip, local_port, destination_ip, destination_port, pid)` tuples; emit only new ones; cap tuples kept (e.g. 20 000) and expire entries not seen for 24 h.

### `collectors/listening.py`
`psutil.net_connections(kind="inet")` filtered to `LISTEN`. Emit `new_listening_port` for `(proto, local_ip, port, pid)` not seen before (first run seeds state silently). `details={"protocol","bind_address","port","bind_scope":"loopback|private|all_interfaces|public"}`, process name when available.

### `collectors/processes.py`
`psutil.process_iter(["pid","ppid","name","username","exe","create_time"])`. State = set of `(pid, create_time)`. First run seeds state and emits only `suspicious_process` events. Afterwards emit `process_started` for new processes (cap `max_process_events_per_run`, warn on truncation). `suspicious_process` when `exe` starts with `/tmp/`, `/var/tmp/`, `/dev/shm/`, `/run/user/` (non-systemd) or the exe is `(deleted)`. **Never store cmdline.**

### `collectors/filesystem.py`
Pure helpers used by drift: `get_file_metadata(path) -> dict | None` (`exists, owner, group, mode "0644", mtime UTC ISO, size, is_symlink, link_target_scope`), `hash_file(path, max_bytes=...) -> str | None` (chunked, returns None on error), `list_directory(path, recursive, max_entries) -> list[entry]` (name, mode, owner, group, size, mtime, sha256 for regular files ≤ size limit), `ssh_key_fingerprints(path) -> list[str]` (parses `authorized_keys` lines, extracts key type + base64 blob, returns `SHA256:<b64>` fingerprints; **never returns key material or comments**; skips malformed lines). Does not follow symlinks outside the target directory.

### `collectors/system.py`
Hourly `system_info`: `details={"hostname","kernel","boot_time","uptime_seconds","cpu_percent","memory_percent","logged_in_users"}`.

## Ingestion `core`-adjacent `engine/ingest.py`
`run_collection(settings, db_path, now=None) -> IngestReport`:
1. For each enabled collector: load state → run → normalize each event (`normalize_event`) → `save_events` → **then** persist new state → `record_collector_run`.
2. One failing collector never stops others; unexpected exceptions are logged with traceback, recorded as `status="error"`.
3. Idempotent: a second run with no new activity inserts nothing.
4. Severity resolution, allowlist and enrichment are applied in Phase 4 (hook already present as no-op pipeline steps).
Migration `m002`: `collector_runs`.

## Worked example (log lines → events)
```
2026-11-15T01:24:19.424500+00:00 srv sshd[812]: Failed password for invalid user admin from 203.0.113.45 port 52114 ssh2
→ {"timestamp":"2026-11-15T01:24:19.424500+00:00","source":"auth_log","event_type":"failed_login","severity":"low",
   "description":"Failed SSH login attempt for admin","username":"admin","source_ip":"203.0.113.45"}

Nov  4 10:30:15 srv sudo:   alice : TTY=pts/0 ; PWD=/home/alice ; USER=root ; COMMAND=/usr/bin/visudo -c
→ event_type "sudo_command", username "alice", process_name "visudo",
  details {"target_user":"root","command_executable":"/usr/bin/visudo","command_args_count":1}   # no "-c" stored
```

## Tests
Each pattern/event type; unrelated line → None; ISO + syslog timestamps; year rollover; incremental read; no-new-lines → nothing; rotation reset; partial final line not consumed; over-long line skipped; invalid UTF-8; permission denied → warning; journald parsing with a faked `subprocess.run` (assert argument list, no shell); `both` mode dedup; dpkg parse; network (SimpleNamespace connections, monkeypatch `psutil`): established, no raddr, empty, missing pid, AccessDenied, repeat snapshot emits nothing; listening first-run silent then new port detected, bind scope classification; processes first-run seed, new process, cap/warn, suspicious path, deleted exe, no cmdline stored; filesystem helpers on `tmp_path` (chmod, symlink, unreadable file, key fingerprints from sample keys, malformed key lines); ingestion idempotence; one collector failing; state persisted only after save. **Fuzz** (`tests/fuzz/`, hypothesis): `parse_auth_line` and the dpkg parser never raise and never return events failing `validate_event` for arbitrary text (including huge, NUL and unicode input).

## Gate
Suite green; `python cli.py init && python cli.py collect` work on this machine (document any auth.log permission warning; never use sudo).
