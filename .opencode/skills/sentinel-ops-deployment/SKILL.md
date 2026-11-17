---
name: sentinel-ops-deployment
description: Operations conventions for Sentinel - engine loop and scheduler, logging, retention, health, systemd hardening examples, reverse proxy, backups, upgrades, Makefile and CI. Load when writing engine/, retention, logging, deploy/, Makefile, CI, or operations docs.
---

# Operations

- **Processes**: `cli.py engine` (collect+analyze loop), `uvicorn api.main:app` (127.0.0.1:8000), `next start` (127.0.0.1:3000 proxying `/api`). SQLite WAL shared; one engine at a time (cycle lock with stale expiry).
- **Scheduler**: pure `next_due(state, now)` state machine; jitter; backoff on repeated failures; SIGTERM/SIGINT finish the current step and release the lock; `--once`.
- **Cycle**: collect → rules → baselines/anomalies → correlate → score → notify → publish; each step isolated, timed, reported (`cycle_runs`).
- **Logging**: JSON lines, rotating (10 MB × 5), redaction filter, request ids in API; never log secrets, contents or args.
- **Retention**: per-severity windows; never prune evidence of open incidents or baselines needed now; dry-run default; audit every prune; optional VACUUM.
- **Health**: `core.health.get_health()`: ok/degraded/down with reasons (engine stale > 3× interval, unreadable logs, DB errors).
- **Deployment docs only** (agent never installs): systemd units run as dedicated `sentinel` user in group `adm`, `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp`, `ReadWritePaths` limited, `ReadOnlyPaths=/etc /var/log`, empty `CapabilityBoundingSet`, `LockPersonality`, `RestrictNamespaces`, `SystemCallFilter=@system-service`, `MemoryMax`; `EnvironmentFile` mode 0600. TLS via reverse proxy; SSE needs `proxy_buffering off`; SSH tunnel is the default remote access.
- **Backups/upgrades**: back up with `sqlite3 .backup` or `VACUUM INTO` before migrations; migrations are forward-only and idempotent.
- **Makefile**: `install test lint fmt api engine web web-test web-e2e openapi demo clean`. **CI**: Python job (ruff, mypy, pytest+coverage) and Web job (lint, typecheck, vitest, build, Playwright on a seeded demo DB); fail if `web/openapi.json` is stale.
- **Never** run `sudo`, install packages system-wide, write outside the project, or open outbound connections as the agent.
