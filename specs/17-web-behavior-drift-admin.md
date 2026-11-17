# Phase 17 — Web: Behavior, Drift, Notifications, Settings, Users, Audit, Health

Skills: sentinel-nextjs-frontend, sentinel-explainability, sentinel-security-hardening, sentinel-ops-deployment, sentinel-testing-workflow.

## 17.1 Behavior monitoring (`/behavior`)
- Metric selector (failed logins/hour, successful logins by user, connections by process, distinct destinations by process, sudo by user) + subject picker (autocomplete from `/baselines`) + range (24 h, 7 d, 30 d).
- **BaselineBandChart**: hourly values line, baseline mean line, band `mean ± zσ` for each configured tier (z from the matching baseline-metric rule), anomaly markers (click → anomaly detail), zero-filled gaps drawn as zero, accessible data-table fallback.
- **Maturity panel**: per metric/subject: `mature` / `learning (6 of 24 hours)` with the reason; immature baselines show a clear "Not enough data yet — no anomalies will be reported" message (never a fake "all clear").
- **Anomaly list**: time, metric/subject, observed, mean, std, threshold, "N standard deviations above normal", severity, link to the `anomaly` event and any incident; plain explanation text from the stored description + caveat "Unusual is not necessarily malicious".
- **Tuning shortcut**: "Edit thresholds" opens the corresponding baseline-metric rule in the rule editor (admin) with the preview/backtest panel pre-filled for this metric.
- Table "Known login IPs per user" (from the `known_login_ips` metric) with first seen/last seen.

## 17.2 Configuration monitoring (`/drift`)
- **Monitored paths table**: path, kind, sensitivity, category, enabled, `metadata_only` (locked on for shadow files with a tooltip), baseline status (clean/drifted with colored text label), last checked, last change, warnings (e.g. "hash unavailable: permission denied"). Admin actions: add/edit/remove path (validated server-side; client-side hints for allowed prefixes), reset built-in, "Check now" (`POST /drift/check`).
- **Path detail drawer/page**: current snapshot vs approved baseline side by side (mode, owner, group, size, mtime, hash prefix — **never contents**); change history timeline (what changed, when, flags like `world_writable`); for dirs: added/removed/modified entries table; for `authorized_keys`: fingerprints added/removed (no key material). **Accept as new baseline** (admin; reason required; confirm dialog explaining that this only updates Sentinel's reference and never changes the file).
- Persistence categories filter (cron, systemd, ssh, sudo, authorized_keys, ld_preload, shell_profile).
- Banner: "Sentinel only observes; it never modifies monitored files."

## 17.3 Notifications (`/notifications`) — admin
Global status ("Notifications are OFF globally in settings.toml" — read-only indicator with instructions). Channel list + editor: kind (webhook/email/telegram); fields per kind; **secret fields accept only an environment variable name** (`SENTINEL_WEBHOOK_SECRET`), never the secret; validation that the variable name matches `^[A-Z][A-Z0-9_]{2,63}$`; the page shows whether the named variable is currently **set** (boolean from `/system/info`, never the value). Routing: min severity, rule/tag filters, escalation-only, quiet hours, cooldown, max/hour, digest. **Send test** button (clearly marked test message) with result. **Log** table (status, channel, incident, time, detail). Warning copy for enabling outbound channels ("Sentinel will send incident titles and severities to this destination").

## 17.4 Settings (`/settings`) — admin for edits
Tabs: **Retention** (policy form with per-severity ages, validation, "Dry run" showing what would be pruned with counts and the protections applied, then "Apply" with typed confirmation); **Display** (timezone for display, density, default time range; stored in `localStorage` — no secrets); **Engine** (read-only view of intervals/collector toggles from `/system/info` plus "Run cycle now" button, rate-limited); **About** (versions, DB size, event counts, oldest event, schema version).

## 17.5 Users (`/users`) — admin
List (username, role, last login, disabled, locked until); create (username, role, temporary password generated client-side shown **once**, forced change on first login), change role, disable/enable, reset password, revoke sessions. Guard rails: cannot disable/demote the last admin; cannot delete self; all audited. Password policy hints (≥12 chars) and strength meter (no external lib).

## 17.6 Audit log (`/audit`) — admin
Filterable (actor, action prefix, target type, time range) cursor-paged table; row expands to a **before/after diff** (JSON diff viewer implemented locally, secrets cannot appear because none are stored); export CSV.

## 17.7 Health (`/health`)
Engine/API status, last cycle report with per-step durations and warnings, per-collector last run + warnings + event counts, queue lag, DB size/growth, retention last run, notification failures, "How to fix" hints for known warnings (e.g. auth.log permission: add the service user to group `adm`; no sudo advice from the app beyond documentation text).

## 17.8 Tests
Vitest: band-chart data builder (zero fill, band math with z, anomaly markers) and immature rendering; maturity text; metric/subject selection URL sync; drift status badges (text), metadata-only lock; accept-baseline dialog requires reason and explains no file changes; no UI element ever renders file content fields; env-var-name validator and "set/not set" display; notification form per kind; retention form validation and dry-run rendering; typed-confirmation behavior; users page guard rails (last admin); one-time password display; audit diff viewer (added/removed/changed); health "how to fix" mapping; viewer cannot access admin routes (redirect/403 page) and admin links hidden. Playwright (demo DB): behavior page shows the seeded anomaly with its explanation; drift page shows the seeded `chmod 777` event and accepting the baseline (in the sandbox demo file) flips status to clean; create a webhook channel pointing at a local test server started by Playwright, send test, see log entry; retention dry-run; create user, login as that viewer, verify read-only; audit page shows the actions performed in the run.

## Gate
All suites green; every route in the sitemap reachable from the sidebar; no page requires a feature not in the API catalogue.
