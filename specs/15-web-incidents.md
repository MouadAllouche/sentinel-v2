# Phase 15 — Web: Incident investigation

Skills: sentinel-nextjs-frontend, sentinel-explainability, sentinel-correlation-incidents, sentinel-testing-workflow.

## Goal
The product's centerpiece: understand an incident quickly, see **why** events were grouped and **why** it was scored, and work it through a status workflow.

## 15.1 Incident list (`/incidents`)
Table (cursor pagination, URL-synced filters): severity, score (`RiskScoreMeter`), title, status, primary IP/user, first/last seen, event count, rules fired (top 3 badges), MITRE badges, assignee. Filters: status (multi), severity (multi), time range, assignee, text, "needs attention" preset (open + high/critical). Sort: risk (default) or recent. Bulk actions (admin): change status of selected incidents (requires a reason for `false_positive`/`resolved`; typed confirmation for >10). Live updates highlight changed rows (SSE `incident.*`).

## 15.2 Incident detail (`/incidents/[id]`)
Header: title, severity badge + score meter, status control (admin; allowed transitions only, reason dialog), assignee select, first/last seen, duration, MITRE badges (labelled "indicative"), **Export** menu (Markdown, JSON, PDF), copy link. Banner caveat always visible: *"Sentinel grouped these events by shared attributes and time proximity. This is not proof of a single actor or of a compromise."* Tabs (URL hash `#timeline`, `#evidence`, `#why-grouped`, `#why-score`, `#graph`, `#notes`, `#history`):

1. **Timeline** — vertical chronological list. Each entry: time (UTC + relative gap to previous, e.g. "+3m 12s"), type icon, severity, summary, `Observed`/`Inferred` badge, link strength badge, rule-finding chips (rule + tier), expandable raw event JSON. Between entries show the **relation reason** ("Same source IP 203.0.113.45…") with strong (solid) / weak (dashed) connector. Inferred statements (e.g. "Possible credential guessing succeeded") are visually distinct and list the evidence entries they cite (hover highlights them). Filters: hide weak links, show only observed, collapse repeated events ("×6 failed_login from 203.0.113.45 between 10:00:03 and 10:04:51" expandable).
2. **Evidence** — table of all events and rule findings with filters; per-row actions (open drawer, add allowlist entry for admins).
3. **Why grouped** — grouping explanation from `/incidents/{id}/explanation`: strong links list, weak links list (clearly flagged "time proximity only"), anchor events, caveats. Plain language, no jargon.
4. **Why this score** — the stored reasons as a table: rule, tier, points, severity, explanation, evidence links; running total; cap/`capped` note; severity basis ("floor from rule X" or "score band"); meta-rules; decay info if enabled. A **"What if?"** panel (admin or viewer, read-only) lets the user toggle rules off to see the recalculated score client-side from the stored reasons (pure arithmetic, labelled "simulation, not saved"). Link on each rule to its editor (`/rules/[id]`).
5. **Graph** — SVG/Recharts-free node-link diagram (implement with plain SVG + a tiny force/circle layout; no new dependency) of IPs, usernames, processes, files, with edges for events/links; strong = solid, weak = dashed; node size ∝ event count; click a node → filters the Evidence tab; accessible alternative: a table "Entities and relationships".
6. **Notes** — append-only analyst notes (admin can add; viewers read); markdown-lite rendering sanitised (no raw HTML), timestamps, author.
7. **History** — status history with actor, reason, time; audit entries related to the incident.

Right rail (sticky on desktop): key facts (primary IP scope via enrichment, users, processes, files touched), severity/score summary, quick actions: "Mark false positive…" (offers "Create allowlist entry…" prefilled), "Create rule from this pattern…", "Copy summary".

## 15.3 Behaviors and edge cases
- Merged incidents (`status=merged`) show a redirect banner to `merged_into`.
- Large incidents (>2 000 events): server-side pagination in Evidence; timeline virtualised/collapsed by default with counts.
- Viewer role: all mutation controls hidden; API enforces.
- Optimistic status change with rollback on error; concurrent edits surfaced via `updated_at` check (409 handling → "Incident changed, reload").
- Loading/empty/error states for every tab; deep links to a specific event within the timeline (`#event-123`).

## 15.4 Component contracts
`<IncidentHeader />`, `<StatusMenu />`, `<Timeline entries />`, `<TimelineEntry />`, `<RelationConnector reason strength />`, `<ExplanationPanel />`, `<ScoreReasonsTable reasons />`, `<WhatIfPanel reasons thresholds />`, `<EntityGraph nodes edges />`, `<NotesPanel />`, `<StatusHistory />`. Pure helpers (`collapseRepeats`, `whatIfScore`, `layoutGraph`) live in `lib/incident/*.ts` with unit tests.

## 15.5 Tests
Vitest: timeline ordering/gap formatting; collapse-repeats helper; inferred vs observed badges; weak connector styling class + text label; caveat banner always rendered; `whatIfScore` equals server math (parametrised with the Phase 10 worked example incl. cap at 100 and boundary severities); graph layout deterministic and no overlapping IDs; status menu shows only allowed transitions; reason required dialogs; viewer sees no controls; markdown-lite sanitisation (script/HTML injection payloads rendered inert); merged banner; 409 handling. Playwright (demo DB): open the standard scenario incident → timeline shows the expected sequence; "Why grouped" lists the weak drift link; "Why this score" total equals header score; change status to resolved with reason; add a note; export Markdown/PDF downloads with non-empty content; viewer cannot add note.

## Gate
Green web + Python suites; the standard scenario incident from the demo DB is fully navigable end to end.
