# Operations

Sentinel runs as three independent processes sharing one SQLite database in WAL mode. This
document is deployment guidance only: no commands here require root, and nothing in Sentinel
remediates or modifies the monitored system.

## Local development

```sh
make install
make test
make lint
python cli.py init --db sentinel.db
python cli.py run --db sentinel.db
python cli.py engine --once --db sentinel.db
python cli.py status --db sentinel.db --json
make api    # FastAPI on 127.0.0.1:8000 (Phase 12)
make web    # Next.js on 127.0.0.1:3000 (Phase 13)
```

## Engine cycle

`python cli.py engine` runs collection, rules, baselines, correlation, scoring, notifications and a
publish step. Collection and analysis intervals come from `config/settings.toml`; a cycle lock in
`app_settings` prevents two engines running concurrently and expires after ten minutes. SIGTERM or
SIGINT finishes the current step and releases the lock. `engine --once` runs a single cycle and
`--no-notify` suppresses outbound delivery. Steps are isolated: a failing step is recorded in
`cycle_runs` and does not stop later steps.

## Health and logs

`python cli.py status --json` reports `ok|degraded|down` with reasons, the last cycle, event count,
oldest event and DB size. Structured JSON logs are written to the console and to `logs/sentinel.log`
(10 MB × 5); fields matching password/secret/token/authorization/cookie are redacted.

## Retention

`python cli.py prune --dry-run` prints the planned deletions without changing data; omitting
`--dry-run` applies them and writes an audit row. Evidence linked to an incident is protected,
baselines needed for the current window are kept, and audit rows are pruned last. `VACUUM` is only
performed when explicitly enabled and never while the API holds long reads.

## Security posture

Run the engine as an unprivileged service account in group `adm` so it can read auth logs. Never run
Sentinel as root. Secrets come only from environment variables; the database stores their names.
Background channels are off until explicitly enabled. binds are loopback-only and TLS is terminated
by a reverse proxy (see `docs/DECISIONS.md` and the deployment examples, which arrive with the web
phases).

## Backups and upgrades

Back up the database before upgrades using `sqlite3 sentinel.db ".backup backup.db"` or
`VACUUM INTO`. Migrations are forward-only and idempotent; each phase appends exactly one. Restore by
stopping all processes, replacing the database file and restarting.
