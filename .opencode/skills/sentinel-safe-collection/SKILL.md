---
name: sentinel-safe-collection
description: Safety and robustness rules for Sentinel collectors (auth.log, journald, dpkg, network, listening ports, processes, filesystem, system) and drift detection. Load when writing or changing anything that reads system state, logs, processes, or monitored files.
---

# Safe collection rules

## Read-only, least privilege
- Only read. Never write to `/etc`, `/var/log`, home dirs or any monitored path. Never `sudo`, `chmod`, `chown`, kill, block, or restart anything.
- Expected failures (`PermissionError`, `FileNotFoundError`, `psutil.AccessDenied/NoSuchProcess/ZombieProcess`, malformed input) are handled **per item**: add a warning, continue. Collectors return `CollectionResult(events, warnings, state)`; they do not raise for these.
- Never escalate privileges. Document what group membership (`adm`) a collector needs.

## Secrets
- `metadata_only` files (and always `/etc/shadow`, `/etc/gshadow`): `os.stat` only; **never open**; `sha256=None`. Tests patch `open`/`hash_file` to fail.
- Other files: SHA-256 + metadata only; never content. `authorized_keys`: fingerprints only (no key material, no comments).
- Never store process cmdlines or sudo argument strings. Store executable (basename/path) and argument count.

## Subprocess and parsing
- `subprocess.run([...], timeout=..., check=False)` with an **argument list**; never `shell=True`. Only `journalctl` is ever executed.
- Treat all log text as untrusted: bounded regexes, line length cap (4096), `errors="replace"`, never interpolate into SQL/paths/shell.
- Incremental reading: persist `{inode, offset}` (or journald cursor); reset on rotation/truncation; consume only complete lines; persist state **after** events are saved.
- Syslog timestamps lack a year: current year; if more than 1 day in the future use the previous year.

## Volume control and state
- Snapshot collectors (network, listening, processes) emit only what is new since the last run; first run seeds state (no flood), except `suspicious_process`. Cap state size and expire stale entries. Cap events per run and warn on truncation.
- Do not follow symlinks outside the intended directory when listing directories; cap entries and file sizes hashed.

## Limits to document honestly
`psutil.net_connections` is a snapshot (short-lived connections can be missed; details may be unavailable without privilege); polling drift detection can miss quick change-and-revert; reading `/var/log/auth.log` needs group `adm` or root.

## Test pattern
Fake psutil with `SimpleNamespace`; `monkeypatch.setattr("collectors.network.psutil.net_connections", lambda kind: [...])`; fake `subprocess.run`; `tmp_path` for files; hypothesis fuzz for parsers (never raise, output always passes `validate_event`).
