# Phase 13 — Next.js foundation (scaffold, API client, auth, layout, design system)

Skills: sentinel-nextjs-frontend, sentinel-api-design, sentinel-security-hardening, sentinel-testing-workflow, frontend-design (if available).

## Goal
A secure, typed, accessible Next.js shell that talks to the FastAPI backend through a same-origin proxy and provides the layout, auth flow, data layer and design system every page in Phases 14–17 reuses.

## 13.1 Stack and scaffolding (in `web/`)
Next.js latest stable with **App Router**, **TypeScript strict** (`noUncheckedIndexedAccess`), Tailwind CSS, shadcn/ui (copied components under `web/components/ui`), TanStack Query, TanStack Table, Recharts, react-hook-form + zod (`@hookform/resolvers`), `openapi-typescript` + `openapi-fetch`, `date-fns` (+ `date-fns-tz` for display timezone), `lucide-react`, Vitest + Testing Library + `jest-dom`, MSW (unit tests only), Playwright, ESLint (next config + `jsx-a11y`), Prettier. `npm` as package manager, `engines` field pins Node LTS; commit `package-lock.json`. Record all versions in `docs/DECISIONS.md`. Add nothing else without asking.

`npm run` scripts: `dev`, `build`, `start`, `lint`, `typecheck`, `test`, `test:e2e`, `gen:api` (runs `openapi-typescript ../web/openapi.json -o lib/api/schema.d.ts`). Makefile targets `web`, `web-test`, `web-e2e`.

## 13.2 Proxy and environment
`next.config` `rewrites`: `/api/:path*` → `http://127.0.0.1:8000/api/:path*` (backend URL from `SENTINEL_API_URL`, default loopback). Same-origin ⇒ no CORS. **Verify that SSE works through the Next proxy** (streaming, no buffering); if it does not, implement the fallback: the stream hook degrades to polling `GET /api/changes?since=` every 10 s (add that endpoint to the API in this phase, with tests) and document the finding in `DECISIONS.md`.
Security headers via `next.config` `headers()`: strict `Content-Security-Policy` (no inline scripts except the nonce Next supports; `connect-src 'self'`; `frame-ancestors 'none'`), `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Permissions-Policy`. `poweredByHeader: false`. No secrets in `NEXT_PUBLIC_*`.

## 13.3 App structure
```
web/
├── app/
│   ├── (auth)/login/page.tsx
│   ├── (app)/layout.tsx            # shell: sidebar, topbar, auth guard
│   ├── (app)/page.tsx              # Overview
│   ├── (app)/events/page.tsx
│   ├── (app)/incidents/page.tsx  (app)/incidents/[id]/page.tsx
│   ├── (app)/rules/page.tsx  rules/new/page.tsx  rules/[id]/page.tsx
│   ├── (app)/severity/page.tsx  (app)/allowlist/page.tsx
│   ├── (app)/behavior/page.tsx  (app)/drift/page.tsx
│   ├── (app)/notifications/page.tsx  (app)/settings/page.tsx
│   ├── (app)/users/page.tsx  (app)/audit/page.tsx  (app)/health/page.tsx
│   ├── error.tsx  not-found.tsx  loading.tsx
├── components/ { ui/, layout/, data-table/, charts/, badges/, forms/, explain/ }
├── lib/ { api/ (client.ts, schema.d.ts, hooks.ts), auth.ts, format.ts, query-keys.ts, sse.ts, utils.ts }
├── tests/ (vitest)  e2e/ (playwright)
└── openapi.json
```
Server vs client components: pages are server components where data is not interactive; all authenticated data fetching goes through the typed client + TanStack Query in client components (cookie auth is browser-managed), with `middleware.ts` redirecting unauthenticated users to `/login` by checking the session cookie's presence (server verification happens on every API call).

## 13.4 API client and data layer
`lib/api/client.ts`: `openapi-fetch` client with `credentials: "include"`, middleware that adds `X-CSRF-Token` (read from the `sentinel_csrf` cookie) to unsafe methods, maps error envelopes to a typed `ApiError`, and on `401` clears caches and redirects to `/login?next=`. `lib/api/hooks.ts`: typed query/mutation hooks per resource with centralised `queryKeys`, sensible `staleTime`, optimistic updates only where safe (rule enable toggle), invalidation on mutation, toast on error. `lib/sse.ts`: `useLiveUpdates()` hook subscribing to `/api/stream`, mapping messages to query invalidations, auto-reconnect with backoff, pause when the tab is hidden, visible connection status, polling fallback.

## 13.5 Auth flow
Login page (react-hook-form + zod), generic error text, lockout message from API (`retry_after`), `next` param validated to be same-origin path, logout, session-expired handling, change-password dialog, role-aware UI: `useMe()` returns `{username, role}`; `<RequireRole role="admin">` hides/disables admin-only controls **and** the API still enforces. No tokens in `localStorage`.

## 13.6 Layout and design system
Responsive shell: collapsible sidebar (Overview, Events, Incidents, Rules, Severity, Allowlist, Behavior, Drift, Notifications, Settings, Users, Audit, Health), topbar (global search for IP/username → events explorer, live-status indicator, theme toggle, user menu). Light/dark/system via CSS variables.
Design tokens: severity colors (low = slate/blue, medium = amber, high = orange, critical = red) with **text/icon labels, never color alone**; **Fact vs Inference badges** (`Observed` solid, `Inferred` dashed outline); `StrengthBadge` (strong/weak); `MitreBadge` (links to attack.mitre.org, labelled "indicative"); `SeverityBadge`; `RiskScoreMeter` (0–100 with band thresholds from `/risk/thresholds`); `RelativeTime` (absolute UTC on hover/title, display timezone from user setting stored locally); `JsonViewer` (collapsible, copy button, redacts nothing because nothing secret is stored); `EmptyState`, `ErrorState` (retry), `Skeletons`; `ConfirmDialog` (typed-confirmation variant for destructive/bulk actions like re-apply or prune); `DataTable` wrapper over TanStack Table with server-side pagination (cursor), column visibility, URL-synced filters (`nuqs`-style via `useSearchParams`, no extra dependency), CSV export button.
Accessibility: WCAG 2.2 AA target; keyboard navigable; focus rings; `aria-live` for toasts and live feed; reduced-motion respect; table semantics; form errors tied to inputs; contrast checked.
Charts wrapper (`components/charts`): `TimeSeriesChart`, `StackedBarChart`, `DonutChart`, `BaselineBandChart` (value line + mean ± zσ band + anomaly markers), each with accessible fallback table and empty/immature states.

## 13.7 Tests
Vitest + Testing Library: login form validation and error display; `ApiError` mapping; CSRF header injected only on unsafe methods; 401 redirect; `RequireRole`; SeverityBadge labels (text present for every level); `DataTable` pagination/filter URL sync; `BaselineBandChart` renders fallback table; `useLiveUpdates` reconnect/backoff and invalidation (fake EventSource); `next` param open-redirect rejection; format helpers (UTC/relative). Playwright smoke: unauthenticated redirect to `/login`, login (against the seeded demo DB + running API), shell renders, theme toggle persists, logout. `npm run lint && typecheck && test && build` pass; CI web job added (`.github/workflows/ci.yml`).

## Gate
Both stacks green; `make web` serves the shell on `127.0.0.1:3000`; screenshot-free manual checklist in `docs/DECISIONS.md` (headers verified with `curl -I`).
