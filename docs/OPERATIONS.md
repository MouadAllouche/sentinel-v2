# Operations

Sentinel runs as three independent processes sharing one SQLite database in WAL mode. This document is deployment guidance only. Nothing in Sentinel remediates or modifies the
monitored system; **runtime needs no root**, but the one-time deployment setup (creating the
service user and writing `/etc/sentinel/sentinel.env`) does require administrator privileges and
is described here for documentation only — the agent never performs it.

## Local development

```sh
make install
make test
make lint
python cli.py init --db sentinel.db
python cli.py run --db sentinel.db
python cli.py engine --once --db sentinel.db
python cli.py status --db sentinel.db --json
make api    # FastAPI on 127.0.0.1:8000
make web    # Next.js on 127.0.0.1:3000
```

## Installation (one-time, requires administrator privileges)

```sh
# Create an unprivileged service account with read access to auth logs (no sudo inside Sentinel).
sudo useradd --system --shell /usr/sbin/nologin --groups adm sentinel
sudo mkdir -p /etc/sentinel /var/lib/sentinel /var/log/sentinel
sudo install -d -m 0750 -o sentinel -g sentinel /var/lib/sentinel /var/log/sentinel

# Install the application as that user (adjust paths to your install location).
sudo -u sentinel python3 -m venv /opt/sentinel/venv
sudo -u sentinel /opt/sentinel/venv/bin/pip install -e /opt/sentinel
cd /opt/sentinel/web && sudo -u sentinel npm ci && sudo -u sentinel npm run build

# Secrets are read from a mode-0600 environment file; the DB stores only variable NAMES.
sudo tee /etc/sentinel/sentinel.env >/dev/null <<'EOF'
SENTINEL_SESSION_KEY=<generate-with: python -c 'import secrets;print(secrets.token_hex(32))'>
SENTINEL_WEBHOOK_SECRET=<only-if-a-webhook-channel-is-enabled>
EOF
sudo chmod 0600 /etc/sentinel/sentinel.env
```

Copy `deploy/sentinel-{engine,api,web}.service.example` into `/etc/systemd/system/`, adjust paths,
then `systemctl daemon-reload && systemctl enable --now sentinel-engine sentinel-api sentinel-web`.
The engine unit denies network egress by default; if you enable outbound notification channels,
remove `IPAddressDeny=any` (documented tradeoff). Terminate TLS at the reverse proxy
(`deploy/reverse-proxy.example.conf`) and keep both API and web bound to `127.0.0.1`.

## First administrator

There are no default credentials. Create the first admin interactively, never through argv:

```sh
sudo -u sentinel /opt/sentinel/venv/bin/python cli.py user create --role admin
# prompts: New password:   (at least 12 characters, entered with getpass)
```

Additional users are created in the dashboard (**Users**). Viewer accounts are read-only.

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
by a reverse proxy. See `deploy/*.service.example` for hardened systemd units and
`deploy/reverse-proxy.example.conf` for TLS, HSTS and SSE-safe proxying (`proxy_buffering off` for
`/api/stream`). The units run as user `sentinel` in group `adm`, read secrets from a mode-0600
environment file and deny all capabilities. Remote access should use an SSH tunnel or a VPN; the
reverse proxy can additionally restrict source IPs. Notification channels that use `IPAddressDeny`
on the engine must be handled explicitly — the documented units deny engine egress by default and
the API/web units do not.

## Backups, upgrades and disaster recovery

Back up the database before upgrades using `sqlite3 sentinel.db ".backup backup.db"` or
`VACUUM INTO 'backup.db'`. Stop all three processes first, replace the database file to restore,
then restart them. Migrations are forward-only and idempotent; each phase appends exactly one, so
upgrading a v-N database applies only the missing migrations. Keep the environment file and the
database backup in separate locations.

In a disaster (lost DB but retained backup): restore the backup, start the API and web, verify
`python cli.py status --json` reports `ok`, and confirm the audit log contains the expected recent
actions. If the DB was lost entirely, recreate it with `cli.py init`, re-create the first admin and
seed defaults/rules with `cli.py seed`; historical evidence cannot be recovered.

## Troubleshooting

- **auth.log permission denied**: the engine user must be a member of group `adm`. Sentinel never
  uses sudo; an unreadable log is recorded as a collector warning and skipped. Add the service user
  to the group at deployment time, not from the application.
- **journald access denied**: grant the service account access to the journal via its group or
  policy; do not run the engine as root. The collector degrades gracefully with a warning.
- **SSE not updating in the dashboard**: ensure the reverse proxy sets `proxy_buffering off` for
  `/api/stream`. The client automatically falls back to polling if streaming cannot be established.
- **Engine stale warning**: check the engine service is running and the cycle lock is not stuck;
  the lock expires after ten minutes.

## Generating evidence safely

`scripts/generate_attack_vm.md` describes a **manual** procedure on a throwaway VM you own to
produce real SSH failures. It is documentation only: Sentinel never automates it, never connects to
another host and never runs it in tests. For day-to-day verification use `python cli.py demo`, which
is fully sandboxed.
