---
name: sentinel-nextjs-frontend
description: Conventions for Sentinel's Next.js dashboard - App Router structure, typed API client from OpenAPI, TanStack Query, forms with zod, SSE live updates, accessibility, design tokens, charts, role-aware UI, and testing with Vitest/Playwright. Load when writing or changing anything under web/.
---

# Next.js frontend

- App Router + TypeScript strict. Pages in `app/(app)/…`; auth routes in `app/(auth)/…`. `middleware.ts` redirects to `/login` when the session cookie is absent (the API is the real authority).
- **Typed client only**: `openapi-typescript` generates `lib/api/schema.d.ts` from `web/openapi.json`; `openapi-fetch` client with `credentials:"include"`, CSRF header on unsafe methods, `ApiError` mapping, 401 → login redirect. No hand-written duplicates of response types.
- Data: TanStack Query hooks per resource, central `queryKeys`, invalidation on mutation, optimistic updates only for safe toggles, toasts on errors. Tables: TanStack Table + **cursor** pagination; filters **synced to the URL**.
- Forms: react-hook-form + zod; server validation errors (`details[].path`) mapped back to fields; `aria-describedby`; unsaved-changes guard; confirm dialogs for destructive/bulk actions (typed confirmation for bulk).
- Live updates: `useLiveUpdates()` on SSE → query invalidations; backoff reconnect; pause when tab hidden; visible status; polling fallback if streaming through the proxy fails.
- Roles: `useMe()`, `<RequireRole role="admin">` hides/disables admin controls; never rely on UI for security.
- Design tokens: severity colors **plus text/icon labels**; `Observed` vs `Inferred` badges; `StrengthBadge`; `MitreBadge` ("indicative"); `RiskScoreMeter`; `RelativeTime` (absolute UTC on hover). Light/dark via CSS variables.
- Charts (Recharts): wrappers with accessible fallback table, empty and "learning/immature baseline" states. Never present immature data as "all clear".
- A11y: WCAG 2.2 AA, keyboard operable (incl. drag-reorder alternatives), focus visible, `aria-live` for live feeds/toasts, reduced motion, labelled controls.
- Security: no secrets in `NEXT_PUBLIC_*`, no tokens in localStorage, sanitise any rendered markdown, validate `next` redirect params, strict CSP; never render file contents (none are provided).
- Performance: server components for static shells, dynamic imports for heavy charts, debounced inputs, cancel in-flight queries, avoid layout shift (skeletons).
- Tests: Vitest + Testing Library (+ MSW) for components/hooks/helpers; Playwright for journeys against a seeded demo DB; every pure helper (`collapseRepeats`, `whatIfScore`, `layoutGraph`, tier↔unit conversion) has unit tests.
- Dependencies: only those listed in AGENTS.md; ask before adding anything.
