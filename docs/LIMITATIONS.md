# Limitations

Sentinel v2 is intentionally conservative. These limits are honest, not bugs to be
discovered in production.

## Collection

- **Polling, not real time.** The engine samples logs and snapshots on an interval. A change that
  is made and reverted between two polls can be missed. There is no inotify/fanotify watcher in v1.
- **Log access.** Reading `/var/log/auth.log` normally requires membership of the `adm` group.
  Sentinel never uses sudo or escalates; unreadable logs produce a warning and are skipped.
- **psutil snapshots.** Network connections and processes are point-in-time views. Short-lived
  connections can be missed, and process details may be unavailable without privilege.
- **Command lines are never stored.** Sudo events keep only the executable and argument count;
  process events never contain cmdlines. This is by design.

## Drift monitoring

- Hashes of large files are capped; only metadata plus a bounded hash are stored.
- `metadata_only` paths (always including `/etc/shadow` and `/etc/gshadow`) are stat-only and are
  never opened. Their contents, modes apart, are not inspected.
- Running unprivileged cannot read all monitored paths; unreadable paths produce warnings and a
  `sha256` of `null`.
- Monitoring is strictly read-only: Sentinel never repairs, reverts, blocks or modifies a
  monitored file or any system configuration.

## Baselines and rules

- Baselines are simple hourly mean/stddev statistics, not machine learning. An immature baseline
  reports `insufficient_baseline` rather than "normal".
- Hour-of-week profiles are optional and currently fall back to the global hourly baseline with an
  explanatory reason.
- All rule points and severity thresholds are **uncalibrated starting points**. They are editable
  and every score stores its reasons, but the numbers are not statistically validated.
- MITRE technique mappings are indicative and have not been verified online; confirm them at
  attack.mitre.org.
- Backtesting currently supports threshold rules only; other kinds return an empty result until
  their backtest support is added, and callers must say so explicitly.

## Scale and scope

- One host, one SQLite database. SQLite WAL allows the engine, API and web processes to share it,
  but this is not a multi-host or high-throughput design.
- Event queries use keyset pagination and indexes; very large retention windows will still grow
  the database until the retention policy prunes it.
- No automatic remediation, no outbound network except explicitly enabled notification channels,
  no DNS/GeoIP lookups, no secrets, file contents or command lines stored.
- The threat simulator (`docs/SIMULATION.md`) models only what reaches logs, connections,
  processes and files. It does not model encrypted traffic, memory-only malware, kernel rootkits,
  zero-days, or a real adversary. Its detection matrix measures rule behaviour on synthetic input,
  not real-world detection performance; the low-and-slow scenario is a known blind spot.
