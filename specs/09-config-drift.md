# Phase 9 — Configuration drift and persistence monitoring

Skills: sentinel-safe-collection, sentinel-security-hardening, sentinel-explainability, sentinel-sqlite-patterns, sentinel-testing-workflow.

## Goal
Detect changes to sensitive files, directories and persistence mechanisms, describing **exactly** what changed. Monitoring is strictly read-only: Sentinel never modifies, repairs or reverts anything, and never stores file contents.

## 9.1 Monitored paths (user-editable, in DB)
Table `monitored_paths` (`m007` together with `file_snapshots`): `path` (absolute, normalised, no `..`), `kind` (`file` | `dir` | `authorized_keys`), `sensitivity` (`low|medium|high|critical`), `category` (`system_account`, `ssh`, `sudo`, `cron`, `systemd`, `authorized_keys`, `ld_preload`, `shell_profile`, `other`), `metadata_only` (bool), `enabled`, `recursive`, `max_entries` (default 2000).
Seeded defaults (builtin, editable, resettable; paths that do not exist are recorded as "absent", not errors):

| path | kind | sensitivity | category | notes |
|---|---|---|---|---|
| `/etc/passwd` | file | high | system_account | |
| `/etc/group` | file | medium | system_account | |
| `/etc/shadow` | file | critical | system_account | **metadata_only = true, enforced** |
| `/etc/gshadow` | file | critical | system_account | metadata_only = true, enforced |
| `/etc/sudoers` | file | critical | sudo | |
| `/etc/sudoers.d` | dir | critical | sudo | |
| `/etc/ssh/sshd_config` | file | high | ssh | |
| `/etc/ssh/sshd_config.d` | dir | high | ssh | |
| `/etc/crontab` | file | high | cron | |
| `/etc/cron.d` , `/etc/cron.daily` , `/etc/cron.hourly` | dir | high | cron | |
| `/var/spool/cron/crontabs` | dir | high | cron | likely unreadable without privilege → metadata only warning |
| `/etc/systemd/system` | dir | high | systemd | |
| `/etc/ld.so.preload` | file | critical | ld_preload | |
| `/etc/profile.d` | dir | medium | shell_profile | |
| `/root/.ssh/authorized_keys`, `~/.ssh/authorized_keys` of the service user | authorized_keys | critical/high | authorized_keys | fingerprints only |

Validation (API and config): reject non-absolute or non-normalised paths; reject paths outside an allow-prefix list unless `allow_custom_paths=true` in settings (default allows `/etc`, `/var/spool/cron`, `/root`, `/home`, `/usr/local`, `/opt`); `/etc/shadow` and `/etc/gshadow` can never have `metadata_only=false`; max 200 paths. **A path in `metadata_only` mode must never be opened** (tests monkeypatch `open`/`hash_file` to fail).

## 9.2 Snapshots — `core/drift_detection.py` (pure) + `collectors/filesystem.py` (I/O)
`Snapshot`: `{path, exists, kind, sha256|None, owner, group, mode "0644", mtime, size, is_symlink, extra}`.
- `kind=file`: hash (unless metadata_only/unreadable) + metadata.
- `kind=dir`: `extra.entries = [{name, mode, owner, group, size, mtime, sha256|None}]` (regular files only hashed, size limit 5 MB, entry cap `max_entries`, `truncated=true` flag); directory metadata itself recorded too.
- `kind=authorized_keys`: `extra.fingerprints = ["SHA256:...", ...]` + `extra.key_count`; the file hash is also kept; **no key material or comments stored**.
- Unreadable → store what `os.stat` yields, `sha256=None`, add a warning `"/etc/crontab: hash unavailable (permission denied)"`, never raise.

## 9.3 Comparison (pure): `compare_snapshots(prev, curr, spec) -> list[Change]`
Change fields: `exists` (file added/removed), `sha256`, `owner`, `group`, `mode`, `mtime`, `size`, directory `entries_added`, `entries_removed`, `entries_modified` (by name + changed fields), `fingerprints_added`, `fingerprints_removed`, `symlink_target_changed`.
Flags computed: `world_writable` (mode gains `o+w`), `group_writable_added`, `world_readable_added` (esp. shadow files), `setuid_added`, `owner_changed_to_nonroot` (for root-owned sensitive paths), `only_mtime` (only mtime changed).
Descriptions are exact: `"/etc/ssh/sshd_config permissions changed from 0644 to 0777"`, `"/etc/cron.d: new file 'backup' (mode 0755, owner root)"`, `"/root/.ssh/authorized_keys: 1 key added (SHA256:Zx3…)"`.

## 9.4 Drift check flow (`engine/` + storage)
- `drift init`: records a **baseline snapshot** per enabled path (`is_baseline=1`) **only if none exists** (`--force` + explicit confirmation to overwrite); audited.
- `drift check` (every analyze cycle, interval configurable): take current snapshot; compare with the **previous snapshot** (so a change is reported exactly once) → emit `config_drift` events; store the new snapshot. Also compute **deviation from the approved baseline** for the dashboard (`baseline_status: clean | drifted`).
- `config_drift` event: `source="filesystem"`, `file_path`, `details={path, kind, sensitivity, category, changed_fields:[...], changes:[{field, old, new}], flags:[...], only_mtime, baseline_status, warnings}`; description = the exact human sentence. Severity comes from overrides/defaults (Phase 4); rules (Phase 6) add findings.
- `accept_baseline(path, actor, reason)`: explicit admin action; sets the current snapshot as the new baseline; audited; never automatic. The monitored file is never touched.
- A file that **appears** where none existed, or **disappears**, is drift. First-ever snapshot of a path produces no drift event.
- Snapshot history retained per retention policy (keep baseline + last N=200 per path).

## Worked example
Baseline: `/etc/ssh/sshd_config` mode 0644 owner root. Someone runs `chmod 777` on it: next check emits `config_drift` with `changes=[{"field":"mode","old":"0644","new":"0777"}]`, `flags=["world_writable"]`, severity via override → `critical`, rule `world-writable-sensitive-file` fires (+40). A second check with no further change emits nothing. `chmod 644` back: new event "permissions changed from 0777 to 0644", flags empty; dashboard shows `baseline_status: clean`. Adding a new key to `authorized_keys` emits "1 key added (SHA256:…)" — fingerprints only.

## Tests (all on `tmp_path`, never real `/etc`)
First snapshot no event; no change no event; content change; chmod 644→777 flags; owner change (skip if not permitted, else monkeypatch `pwd/grp`); group/mode/mtime-only (`only_mtime`); delete and recreate; symlink replacement; dir: file added/removed/modified, truncation flag; authorized_keys add/remove with real sample keys (fingerprint correctness) and malformed lines; metadata_only never opened (patched open raises); unreadable file warning; path validation (traversal, relative, disallowed prefix, forced metadata_only for shadow); seed/reset; baseline init refuses overwrite; accept baseline audited; reported-once property; baseline_status transitions; performance with 2000 entries; hypothesis: compare is symmetric-safe and never raises on arbitrary snapshots.

## Gate
Green suite; mypy strict on `core/drift_detection.py`; `docs/LIMITATIONS.md` explains: polling interval means short-lived changes can be missed; no real-time inotify in v1; hash of large files capped; running unprivileged cannot read all paths.
