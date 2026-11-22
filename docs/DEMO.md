# Demo

The demo is fully sandboxed. It writes only under `demo_workdir/`, reads no real logs, uses no sudo,
and makes no outbound network calls. All "system" data is synthetic.

```sh
python cli.py demo            # create demo_workdir/ and print the one-time password
make demo-api                 # API on 127.0.0.1:8000 against demo_workdir/demo.db
make web                      # dashboard on 127.0.0.1:3000
```

Open `http://127.0.0.1:3000/login`, use user `demo-admin` and the password printed once by the demo
command. A read-only `demo-viewer` uses the same password. To recreate from scratch, run
`python cli.py demo --reset` (this deletes everything inside `demo_workdir/`).

## What is generated

- `demo_workdir/auth.log`: seven days of benign logins and sudo, then the standard scenario —
  two bursts of failed SSH logins from `203.0.113.45` (6 in 5 minutes, then 30 in 40 seconds), a
  successful login, `sudo visudo`, benign noise from an allowlisted IP.
- `demo_workdir/etc/`: a fake tree with `sshd_config`, `sudoers.d/`, `cron.d/backup` and
  `authorized_keys` containing sample **public** keys only. Permissions on `sshd_config` are changed
  to `0777` after the baseline to demonstrate drift.
- `demo_workdir/demo.db`, `demo_workdir/settings.toml` and `demo_workdir/credentials.json`
  (mode 0600, for the Playwright harness). The password is random and printed only once.
- Synthetic network, package and anomaly events; baseline anomalies appear after the burst.
- Two engine cycles: the second changes nothing (idempotence).

## Demo summary

The command prints incidents with scores/severities, a short timeline excerpt, grouping reasons,
rule findings by tier, anomaly and drift explanations, the local notification log and the commands
above. The dashboard then shows the overview KPIs, the events explorer, the incident walkthrough,
rule tiers firing (5/20/50), drift findings and the allowlisted-but-stored evidence.

`python cli.py demo --live` is an optional interactive mode: each prompt appends a real synthetic
failed-login line to `auth.log` and re-runs collection, so the dashboard's live feed can be shown.
It does not start a background process. `--no-print-password` is used by the end-to-end harness,
which reads credentials from the mode-0600 file instead.

## Threat simulator

`python cli.py simulate run all` runs 19 sandboxed scenarios through the same pipeline and prints
an honest detection matrix, including the deliberate low-and-slow blind spot. Use
`python cli.py simulate dashboard` to load the combined "realistic week" database into the normal
dashboard. The simulator is separate from the demo: it writes only to `sim_workdir/`, uses synthetic
log lines and fake feeds, and never reads the monitored machine. See `docs/SIMULATION.md`.
