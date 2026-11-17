# Sentinel — rules for coding agents (auto-loaded every session)

Sentinel = advanced, **read-only** security monitoring for ONE Linux server.
Python engine (collect → normalize → store → rules → correlate → baselines → drift → score → notify) + FastAPI backend + Next.js dashboard.

Authoritative docs, in priority order: this file → `SENTINEL_MASTER_PROMPT.md` (architecture, global specs) → `specs/NN-*.md` (the phase you are in). On conflict: stop and ask. Progress: `PROGRESS.md`. Assumptions/deviations: `docs/DECISIONS.md`.

## Stack
- Python 3.12 in `./venv`: fastapi, uvicorn, pydantic v2, psutil, httpx, reportlab; dev: pytest, pytest-cov, hypothesis, ruff, mypy. Stdlib: sqlite3, tomllib, hashlib, hmac, ipaddress, argparse, logging, smtplib.
- Web: Node LTS, Next.js (latest stable, App Router), TypeScript strict, Tailwind, shadcn/ui, TanStack Query + Table, Recharts, react-hook-form + zod, openapi-typescript, Vitest + Testing Library, Playwright. No other dependencies without asking.
- Flat Python layout: `core/ collectors/ storage/ engine/ api/ tests/`, entry `cli.py`. Frontend in `web/`.
- Commands: `make test` · `make lint` · `make api` · `make web` · `make demo` · `python cli.py <cmd>`.

## Safety rules (never violate)
1. Never run `sudo`; never write outside the project folder; never write to monitored paths (`/etc`, `/var/log`, home dirs).
2. Sentinel never remediates: no blocking IPs, killing processes, changing permissions or config of the monitored system. Its only writes are to its own SQLite DB and its own log/export files.
3. Never read, store, log or display `/etc/shadow` contents or any secret. Hash + metadata only for monitored files; SSH keys → fingerprints only; never store full process command lines.
4. No machine learning. No outbound network calls except explicitly enabled notification channels. No DNS/GeoIP lookups. No `shell=True`, `eval`, `exec`. SQL always parameterised.
5. Tests never touch the real DB, `/var/log`, `/etc`, the real network, or real SMTP/webhooks. Use `tmp_path`, fixtures, `monkeypatch`, fake transports.
6. Permission errors degrade gracefully (warning, continue). Never escalate privileges.
7. Secrets (SMTP password, bot tokens, webhook secrets, session key) come from environment variables; the DB stores only the env-var **name**. Never commit `.env`.

## Data conventions
- Event required fields: `timestamp, source, event_type, severity, description`. Severities: low/medium/high/critical.
- Stored timestamps: UTC ISO 8601 `+00:00`. Inject `now` into anything time-dependent.
- `source_ip` = remote initiator; `local_ip` = this host; `destination_ip/port` = outbound remote end.
- `event_hash` = SHA-256 of canonical JSON **excluding `severity`, `severity_source`, `enrichment`** (so editing severities never duplicates events).
- Every storage function takes an optional `db_path`. `core/` is **pure** (no DB, no clock, no filesystem): functions take data and return results. I/O lives in `storage/`, `collectors/`, `engine/`, `api/`.
- User-editable configuration lives in the DB (rules, severity defaults/overrides, allowlist, monitored paths, notification channels, thresholds, retention) and is seeded from built-in defaults that are always restorable ("reset to default"). `config/settings.toml` holds only static/bootstrap settings.
- Every mutation of user config writes an `audit_log` row (who, what, before, after).

## Working rules
- Test-first. Run the **whole** suite before saying a phase is done. Never weaken a test to pass.
- One phase at a time; stop and report; wait for "continue". Commit `phase-N: summary`.
- No stubs/TODOs/`pass` placeholders in delivered code. No unrequested features.
- Wording: "possible", "suspicious", "consistent with". Never "attack confirmed". Keep observed facts and inferences separate in data and UI.
- Idempotence: collecting/analysing twice never duplicates events, findings, incidents or notifications.
- After each phase run the `reviewer` subagent (`/review N`) and fix every blocker before reporting.

## Skills (load on demand)
sentinel-event-schema · sentinel-safe-collection · sentinel-sqlite-patterns · sentinel-rules-engine · sentinel-correlation-incidents · sentinel-explainability · sentinel-api-design · sentinel-security-hardening · sentinel-nextjs-frontend · sentinel-ops-deployment · sentinel-testing-workflow · sentinel-docs-writing · sentinel-review-checklist
