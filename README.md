# Sentinel

Read-only security monitoring for one Linux server. Sentinel collects evidence,
normalises it, applies user-defined rules, groups related events into explained
incidents, learns behavioural baselines, detects configuration drift, scores risk
transparently, and presents everything in a local dashboard. It never remediates,
never stores secrets, file contents or command lines, and never escalates
privileges.

**Status**: all 18 phases complete. See `PROGRESS.md` for evidence and `specs/` for the original
phase requirements.

## Quick start — six commands to a working demo

```sh
python3 -m venv venv && make install       # 1. Python environment
cd web && npm ci && cd ..                  # 2. Frontend dependencies
make test && make lint && make web-test    # 3. Verify both stacks
python cli.py demo                         # 4. Build the sandboxed demo (prints a one-time password)
make demo-api                              # 5. API on 127.0.0.1:8000 against demo.db (terminal 2)
make web                                   # 6. Dashboard on 127.0.0.1:3000 (terminal 3)
```

Open `http://127.0.0.1:3000/login` and sign in as `demo-admin` with the printed password. The demo
never touches real logs or system files; see `docs/DEMO.md`.

Python 3.12, Node LTS and npm are required. Tool versions and design decisions are recorded in
`docs/DECISIONS.md`. Architecture: `docs/ARCHITECTURE.md`; security model: `docs/SECURITY.md`.

## Safety

- **Disabling an event type discards its evidence.** Event-type defaults are editable in the
  database; setting `enabled=false` makes ingestion skip that type entirely, so those events are
  never stored and cannot be recovered by re-enabling or by re-applying severities. A collector
  warning is recorded whenever this happens. Prefer an allowlist entry with a reason when you only
  want to suppress alerts.
- Nothing writes outside the project directory; the monitored system is never modified.
- All configuration that users edit lives in SQLite and is seeded from restorable defaults.
- Secrets come only from environment variables; the database stores their names.
- No sudo, no machine learning, no outbound network except explicitly enabled
  notification channels.

## Threat simulator

`python cli.py simulate list` shows 19 synthetic scenarios (attacks, benign days and a deliberate
low-and-slow blind spot). `python cli.py simulate run all` replays them through the real pipeline
and prints a detection matrix; `simulate dashboard` builds a combined scenario database for the
dashboard; `simulate whatif <scenario> --rules FILE.json` compares an exported rule set with the
defaults. Everything is written to `sim_workdir/`; no real logs, network calls or privileged
operations are used. See `docs/SIMULATION.md`.

See `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/LIMITATIONS.md` and
`docs/SIMULATION.md`.
