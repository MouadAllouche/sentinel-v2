# Sentinel

Read-only security monitoring for one Linux server. Sentinel collects evidence,
normalises it, applies user-defined rules, groups related events into explained
incidents, learns behavioural baselines, detects configuration drift, scores risk
transparently, and presents everything in a local dashboard. It never remediates,
never stores secrets, file contents or command lines, and never escalates
privileges.

**Status**: Phase 0 (bootstrap) complete. Detection and dashboard phases are
implemented one at a time; see `PROGRESS.md` and `specs/` for the roadmap.

## Development

```sh
python3 -m venv venv
make install
make test
make lint
```

Python 3.12, Node LTS and npm are required. Tool versions and all design decisions
are recorded in `docs/DECISIONS.md`.

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

See `docs/DECISIONS.md` and, as they are written, `docs/ARCHITECTURE.md`,
`docs/SECURITY.md` and `docs/LIMITATIONS.md`.
