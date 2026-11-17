# Phase 14 — Web: Overview and Events explorer

Skills: sentinel-nextjs-frontend, sentinel-explainability, sentinel-testing-workflow.

## Goal
The two most-used pages: a live Overview and a powerful Events explorer. Read-only except for saved filters and exports.

## 14.1 Overview (`/`)
Layout (responsive grid, loading skeletons per card, per-card error state):
1. **KPI row**: events (24 h, with delta vs previous 24 h), failed logins (24 h), open incidents, critical/high incidents, active rule findings (24 h), suppressed (allowlisted) events (24 h), active network connections seen (24 h). Each KPI links to the relevant filtered page.
2. **Events over time** (stacked bars by severity, hour buckets for 24 h / day buckets for 7 and 30 days; range switch 24 h | 7 d | 30 d); zero-filled series from `/events/stats`.
3. **Event types** donut + **Top source IPs**, **Top usernames**, **Top processes** (from `/events/top`), each item links to the events explorer with that filter.
4. **Highest-risk open incidents** (top 5 by score, with SeverityBadge, RiskScoreMeter, title, first/last seen, MITRE badges) → incident detail.
5. **Live feed** of the latest 20 events (via SSE; pause/resume button; `aria-live="polite"`; new rows highlighted briefly; respects reduced motion). Shows connection status ("Live" / "Reconnecting…" / "Polling").
6. **System health strip**: engine last cycle (age + status), collector statuses with warnings (e.g. "auth.log: permission denied"), DB size, baseline maturity ("learning: 6/24 h"), notifications enabled/disabled. Links to `/health`.
7. **Rule activity**: findings in the last 24 h grouped by rule (top 5) with sparkline.
Empty states: first run (no events) shows a checklist ("Run the engine", "Check collector warnings", link to docs) instead of empty charts.

## 14.2 Events explorer (`/events`)
- **Filter bar** (all URL-synced and shareable): multi-select event type (grouped: Authentication, Network, Process, Configuration, System, Detection), severity multi-select, source, username, IP (exact or CIDR input validated client-side), process, time range (presets: 15 m, 1 h, 24 h, 7 d, custom with UTC/local toggle), free-text search, "include allowlisted" toggle (default on, shows a badge), "only in incidents" toggle.
- **Saved filters**: save/load/delete named filters (per user, via `/filters/saved`).
- **Table** (server-side cursor pagination, 50/100/200 per page, sticky header, column picker): time (relative + absolute title), severity (with source tooltip: "default", "override: <name>", "rule: <id>"), type, source, description, username, source IP, process, score, incident link(s). Row click opens a **detail drawer**.
- **Detail drawer**: summary; `Observed` badge; full normalized JSON in `JsonViewer`; enrichment panel (ip_scope, flags); severity explanation (which default/override produced it, with a link to `/severity`); related findings (rules + tier) and incidents; **context actions**: "Show events from this IP", "Show events for this user", "Add allowlist entry…" (admin; prefilled dialog requiring a reason), "Create rule from this event…" (admin; opens the rule builder with a template matched to the event type). Copy-as-JSON button.
- **Quick stats** above the table for the current filter: total, by severity mini-bars, time histogram brush (select range to narrow the time filter).
- **Export**: CSV/JSON of the current filter (server caps at 100 000 rows; UI explains the cap) — triggers `/events/export` with the same filter params.
- **Live mode** toggle: prepend new matching events without losing scroll position; "N new events — click to load" banner pattern when scrolled down.
- Keyboard: `/` focuses search, `j/k` moves selection, `Enter` opens drawer, `Esc` closes.
- Performance: virtualised rows (TanStack Virtual only if already allowed; otherwise paginate), debounced text inputs, cancelled in-flight requests on filter change.

## 14.3 Component contracts
`<EventTable filters onFiltersChange />`, `<EventDrawer eventId />`, `<FilterBar />`, `<KpiCard label value delta href />`, `<TopList field />`, `<LiveFeed />`, `<HealthStrip />`. Types come only from the generated API schema; no hand-written duplicate response types.

## 14.4 Tests
Vitest: KPI delta formatting; filter ↔ URL round trip (including arrays and CIDR validation); saved filter apply; drawer shows severity-source explanation for default/override/rule; allowlist dialog requires a reason; admin-only actions hidden for viewers; live feed pause/resume; "N new events" banner; empty first-run state; error state retry; severity text labels present (no color-only). MSW-backed integration tests for pagination (no duplicates/gaps across pages). Playwright (seeded demo DB + live API): load Overview and see seeded KPIs; click a top IP → filtered events; open drawer and see JSON; export CSV download starts; viewer account cannot see admin actions. Accessibility: `axe` checks (via `@axe-core/playwright` only if the dependency is approved in `DECISIONS.md`) on both pages.

## Gate
Web lint/typecheck/tests/build green; Playwright specs for these pages pass against the demo DB (generated in Phase 18's fixture — until then use the integration-test seed script `scripts/seed_demo_db.py`, created in this phase and reused later).
