# Phase 0 — Bootstrap and tooling

Skills: sentinel-testing-workflow, sentinel-ops-deployment, sentinel-docs-writing.

## Goal
An empty folder becomes a reproducible, linted, tested Python project with CI, configuration loading and time utilities. No security logic yet.

## Tasks
1. `git init`; `python3 -m venv venv`; `.gitignore` (venv/, __pycache__/, .pytest_cache/, .mypy_cache/, .ruff_cache/, *.db, *.db-wal, *.db-shm, logs/, demo_workdir/, web/node_modules/, web/.next/, .env, coverage artifacts, exports/).
2. `pyproject.toml`: project metadata, `requires-python = ">=3.12"`; runtime deps (fastapi, uvicorn, pydantic>=2, psutil, httpx, reportlab) and optional-dependency group `dev` (pytest, pytest-cov, hypothesis, ruff, mypy, types-psutil); `[tool.pytest.ini_options]` (`pythonpath = ["."]`, `testpaths = ["tests"]`, `addopts = "-q"`); `[tool.ruff]` (line-length 100, rules E,F,I,B,UP,S,SIM; `S101` ignored in tests); `[tool.mypy]` (strict for `core/`, lenient elsewhere). Install with `pip install -e ".[dev]"`.
3. `Makefile` targets: `install`, `test`, `lint` (ruff check + ruff format --check + mypy), `fmt`, `api`, `engine`, `web` (placeholder until Phase 13), `demo`, `clean`.
4. `.env.example` listing every env var (`SENTINEL_CONFIG`, `SENTINEL_DB_PATH`, `SENTINEL_SESSION_KEY`, SMTP/Telegram/webhook secret **names** as examples, all commented) — no real values.
5. `.github/workflows/ci.yml`: Python job (3.12): install, ruff, mypy, pytest with coverage; Web job added later (leave a commented stub with a TODO-free note in docs/DECISIONS.md that it is added in Phase 13).
6. Package skeleton with `__init__.py`: `core/ core/rules/ core/notifications/ collectors/ storage/ engine/ api/ api/routers/`.
7. `core/timeutil.py`: `utc_now()`, `to_utc_iso(value, assume_local=True)`, `parse_ts(s) -> aware datetime`, `floor_hour(dt)`, `window_bounds(...)` helpers. Pure except `utc_now`.
8. `core/config.py` + `config/settings.toml`: dataclass tree `Settings`, loaded with `tomllib`, merged over defaults, validated (types, ranges, paths expand `~`), env overrides. Static settings only (see master prompt 4.3). Default file:

```toml
[paths]
database = "sentinel.db"
auth_log = "/var/log/auth.log"
dpkg_log = "/var/log/dpkg.log"
log_dir  = "logs"

[time]
naive_timezone = "local"

[collectors]
auth_source = "auth_log"            # "auth_log" | "journald" | "both"
journald_unit = "ssh"
network = true
listening = true
processes = true
filesystem = true
dpkg = true
system = true
max_process_events_per_run = 200

[engine]
collect_interval_seconds = 60
analyze_interval_seconds = 60
retention_interval_hours = 24

[api]
host = "127.0.0.1"
port = 8000
session_idle_minutes = 120
session_absolute_hours = 12

[notifications]
enabled = false                     # global kill switch, default off
```
9. `tests/conftest.py` with an **autouse** fixture that sets `SENTINEL_DB_PATH` and `SENTINEL_CONFIG` to tmp paths; fixtures `NOW` (fixed aware datetime), `make_event(**overrides)`, `tmp_db`.
10. `PROGRESS.md` (the phase checklist from the master prompt), `docs/DECISIONS.md` (first entries: versions detected, defaults chosen), stub `README.md`.

## Worked example — `to_utc_iso`
```python
to_utc_iso("Nov  4 10:30:15", assume_local=True, year=2026)   # -> "2026-11-04T10:30:15+01:00" converted -> UTC
to_utc_iso("2026-11-15T01:24:19.424500+00:00")                # -> "2026-11-15T01:24:19.424500+00:00"
to_utc_iso("garbage")                                         # -> ValueError
```

## Tests
Config defaults; file overrides merge; unknown keys rejected with a clear error; env overrides; relative paths anchored to project root; timeutil: naive→UTC with a patched local tz, aware→UTC, ISO with microseconds, invalid input, `floor_hour`.

## Gate
`make install && make test && make lint` pass in a fresh venv; first commit exists.
