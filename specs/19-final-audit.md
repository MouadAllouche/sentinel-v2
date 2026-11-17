# Phase 19 — Final audit

Skills: sentinel-review-checklist, sentinel-security-hardening, sentinel-docs-writing.

## Tasks
1. Run every suite and linters; paste the summary lines (pytest incl. coverage %, mypy, ruff, vitest, playwright, `npm run build`).
2. Run the `reviewer` and `security-auditor` subagents across the whole repository; fix every blocker; list remaining non-blockers.
3. Walk `SENTINEL_MASTER_PROMPT.md` sections 1, 4 and 7 and `PROGRESS.md`: for each requirement give evidence (file path + test name). Mark anything partially done honestly.
4. Verify the **user-control requirements** explicitly, with test names: custom threshold rule with ≥2 tiers and windows; edit default severity; override with conditions; allowlist with reason/expiry; reset to defaults for rules, severities and overrides; backtest; versions/restore; audit entries.
5. Security verification: no secrets/contents/command lines persisted (DB inspection query on the demo DB: scan `event_data` for `cmdline`, known fake secrets planted in the demo and tests); no writes outside project or to monitored paths (strace-free: static scan + tests); no outbound network by default (grep + a test that fails on any socket creation in the default config); headers present; cookie flags; CSRF/RBAC matrix complete; dependency list vs `DECISIONS.md`; `npm audit` and `pip-audit` results recorded if the tools are available (do not install them without asking).
6. Performance and scale notes: measured numbers for ingestion rate, rule evaluation over 200k events, API list latency, DB size per 100k events; state limits honestly.
7. Produce `docs/AUDIT_REPORT.md`: requirement matrix, test evidence, known limitations, open risks, suggested future work (inotify drift, multi-host agents, GeoIP, ML-assisted baselines, Docker packaging, i18n).

## Gate
Report delivered; all blockers resolved or explicitly accepted by the user.
