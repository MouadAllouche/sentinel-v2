# Phase 12 — FastAPI backend (auth, RBAC, CSRF, REST, SSE, OpenAPI)

Skills: sentinel-api-design, sentinel-security-hardening, sentinel-sqlite-patterns, sentinel-testing-workflow.

## Goal
A thin, secure, fully typed HTTP API over the engine's data and configuration. It is the **only** interface the Next.js dashboard uses.

## 12.1 Application shape
- `api/main.py`: `create_app(settings=None, db_path=None) -> FastAPI` factory (tests pass a tmp DB); lifespan opens/validates DB (`init_db`); routers under `/api`; OpenAPI at `/api/openapi.json`; docs UI only when `api.docs_enabled` (default false in production).
- Binds `127.0.0.1:8000` by default; refuses to start on a non-loopback host unless `api.allow_remote=true` **and** a `trusted_proxy`/TLS note is set (documented).
- `api/schemas.py`: pydantic v2 response/request models; every endpoint has `response_model` and typed errors `{error: {code, message, details?}}`; consistent pagination `{items, next_cursor}`; ISO-8601 UTC timestamps; ids as ints (events/incidents) or slugs (rules).
- No business logic in routers: validate → call `core`/`storage` → serialize. Database access through a per-request dependency; read endpoints use read-only connections where possible (`mode=ro` URI) and short timeouts.

## 12.2 Security (details in skill `sentinel-security-hardening`)
- **Users**: `users` table, `core/auth.py`: password hashing with `hashlib.scrypt` (n=2^15, r=8, p=1, 16-byte random salt, 32-byte key; encoded `scrypt$n$r$p$salt$hash`), constant-time verification (`hmac.compare_digest`), min length 12, common-password rejection (small embedded list), rehash-on-login if parameters changed. First admin only via `python cli.py user create --role admin` (interactive). **No default credentials. No self-registration.**
- **Sessions**: random 256-bit token; DB stores only SHA-256 of it; cookie `sentinel_session` (`HttpOnly`, `SameSite=Strict`, `Secure` when served over HTTPS/behind proxy flag, `Path=/`); idle timeout (`session_idle_minutes`) + absolute timeout (`session_absolute_hours`); rotate on login; revoke on logout/password change/user disable; admin can list/revoke sessions.
- **CSRF**: double-submit: server sets `sentinel_csrf` (non-HttpOnly) = HMAC(session id, `SENTINEL_SESSION_KEY`); every unsafe method (`POST/PUT/PATCH/DELETE`) requires header `X-CSRF-Token` equal to it; plus `Origin`/`Host` check.
- **Login protection**: failed attempts counted per username **and** per IP; 5 failures / 15 min → lock 15 min (exponential on repeats), uniform error message and timing (verify against a dummy hash when the user does not exist), all audited.
- **RBAC**: `viewer` can read everything non-sensitive; `admin` can mutate rules, severities, overrides, allowlist, monitored paths, thresholds, retention, notification channels, users, incident status/notes (viewer cannot write notes), trigger engine runs, accept baselines, re-apply severities. Dependency `require_role("admin")`.
- **Headers**: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on authenticated JSON, `Permissions-Policy` minimal. No CORS (same-origin through the Next.js proxy); if `cors_origins` configured, exact origins only, credentials allowed only for them.
- **Input hardening**: pydantic `extra="forbid"`; max body size (1 MB; 2 MB for rule import); bounded query params (`limit ≤ 500`); parameterised SQL; regex/condition validation from Phase 4; rate limit on expensive endpoints (backtest, export, re-apply) per user.
- **Audit**: every mutation writes `audit_log` with actor, action, before/after (secrets never present), client IP.
- Responses never contain password hashes, session tokens, env-var **values** (only names), or file contents.

## 12.3 Endpoint catalogue (all under `/api`, JSON unless stated)

**Auth**: `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` · `POST /auth/password` (change own) · `GET /auth/sessions` · `DELETE /auth/sessions/{id}`.
**Events**: `GET /events` (filters: `event_type[]`, `severity[]`, `source[]`, `username`, `source_ip`, `process_name`, `since`, `until`, `search`, `allowlisted`, `incident_id`, `cursor`, `limit`) · `GET /events/{id}` (full normalized JSON + links to incidents/findings + event score) · `GET /events/stats?bucket=hour|day&since&until&group=event_type|severity` (zero-filled time series) · `GET /events/top?field=source_ip|username|process_name&limit` · `GET /events/export?format=csv|json` (streamed, admin or viewer) · `POST /events/reapply-severity` (admin; body `{filters, dry_run=true}`).
**Incidents**: `GET /incidents` (filters: status, severity, since, assignee, search; sort `risk|recent`) · `GET /incidents/{id}` · `GET /incidents/{id}/timeline` · `GET /incidents/{id}/explanation` · `GET /incidents/{id}/graph` (nodes: ips, users, processes, files; edges: events/links, weak/strong) · `POST /incidents/{id}/status` (admin) · `GET|POST /incidents/{id}/notes` · `PATCH /incidents/{id}` (assignee) · `GET /incidents/{id}/export?format=md|json|pdf`.
**Rules**: `GET /rules` · `POST /rules` · `GET /rules/{id}` · `PUT /rules/{id}` · `DELETE /rules/{id}` (custom only, soft) · `POST /rules/{id}/enable|disable|reset` · `GET /rules/{id}/versions` · `POST /rules/validate` (returns errors/warnings) · `POST /rules/preview` (unsaved definition → backtest) · `POST /rules/{id}/backtest` · `GET /rules/findings` (filters, cursor) · `GET /rules/schema` (JSON Schema + field/op catalogue for the UI builder) · `POST /rules/import` · `GET /rules/export`.
**Severity**: `GET /severity/defaults` · `PUT /severity/defaults/{event_type}` · `POST /severity/defaults/{event_type}/reset` · `POST /severity/defaults/reset` · `GET|POST /severity/overrides` · `PUT|DELETE /severity/overrides/{id}` · `POST /severity/overrides/{id}/reset` · `POST /severity/overrides/reorder` · `GET|PUT /risk/thresholds` · `GET|PUT /risk/decay`.
**Allowlist**: `GET|POST /allowlist` · `PUT|DELETE /allowlist/{id}` · `GET /allowlist/stats` (suppressed counts).
**Behavior**: `GET /baselines` · `GET /baselines/series?metric&subject&since` (hourly values + band + maturity) · `GET /anomalies` · baseline parameters are edited via baseline-metric **rules**.
**Drift**: `GET /drift/paths` · `POST /drift/paths` · `PUT|DELETE /drift/paths/{id}` · `POST /drift/paths/{id}/reset` · `GET /drift/status` (per path: last snapshot, baseline status, warnings) · `GET /drift/paths/{id}/history` · `POST /drift/accept` (admin; body path + reason) · `POST /drift/check` (admin; run now).
**Notifications**: `GET|POST /notifications/channels` · `PUT|DELETE /notifications/channels/{id}` · `POST /notifications/channels/{id}/test` · `GET /notifications/log`.
**System**: `GET /health` (unauthenticated minimal `{status}`; detailed for authenticated) · `GET /collectors` (last runs/warnings) · `GET /cycles` · `POST /engine/run` (admin; runs one cycle, rate-limited) · `GET|PUT /settings/retention` · `POST /retention/dry-run` · `POST /retention/apply` (admin) · `GET /system/info` (versions, DB size, counts).
**Users/Audit/Filters**: `GET|POST /users` · `PATCH /users/{id}` (role, disabled) · `POST /users/{id}/password-reset` · `GET /audit` (filters, cursor) · `GET|POST /filters/saved` · `DELETE /filters/saved/{id}`.
**Stream**: `GET /stream` — Server-Sent Events (`text/event-stream`), authenticated by cookie, emits `{type: "event.new"|"incident.created"|"incident.updated"|"finding.new"|"health.changed", id, at}` (ids only; the client refetches), heartbeats every 15 s, `Last-Event-ID` resume from the `changes` table, per-user connection cap, proper cleanup on disconnect.

## 12.4 OpenAPI contract
The generated OpenAPI is committed as `web/openapi.json` (a `make openapi` target regenerates it; CI fails if it is stale). The frontend client types are generated from it (Phase 13).

## 12.5 Worked example
```
POST /api/auth/login {"username":"admin","password":"…"} → 200, Set-Cookie sentinel_session, sentinel_csrf
PUT  /api/rules/ssh-bruteforce-by-ip   (X-CSRF-Token: …, body: tiers[ {5,600,medium,15}, {20,600,high,30} ])
  → 200 {rule, warnings: []}  and audit row {action:"rule.update", before:{...}, after:{...}}
POST /api/rules/preview {definition, since:"2026-11-08T00:00:00Z", until:"2026-11-15T00:00:00Z"}
  → 200 {total_findings: 12, by_severity: {medium: 9, high: 3}, groups: [...], noise_per_day: 1.7, samples: [...]}
PUT  /api/rules/… as viewer → 403 {"error":{"code":"forbidden",...}}
PUT  /api/rules/… without CSRF header → 403 {"error":{"code":"csrf_failed"}}
```

## Tests (`tests/api/`, FastAPI `TestClient` with tmp DB; no real network)
Auth: login success/failure uniform errors, lockout, session expiry (fake clock), logout revokes, password change revokes other sessions, cookie flags, hash never returned. CSRF: missing/invalid/valid; Origin mismatch. RBAC matrix over **every** mutating endpoint (parametrised from the OpenAPI schema: any non-GET without admin → 403/401). Validation: rule validation errors have JSON paths; oversized body → 413; unknown fields → 422; bounded `limit`. Each router: happy path, filters, pagination consistency, 404s. Rules: create/update/version bump/reset/soft-delete/builtin-delete forbidden/preview/backtest limits/import-export round trip. Severity: edit default → new events use it; reapply dry-run vs real; overrides reorder. Allowlist reason required, expiry. Drift path validation incl. shadow forced metadata-only. Incidents: status transition matrix, notes, graph shape, exports content types. SSE: auth required, heartbeat, resume from `Last-Event-ID`, disconnect cleanup. Health unauth vs auth shape. Audit rows for every mutation (parametrised). OpenAPI snapshot test (committed file is current). Security headers present. Performance: events query with 200k rows < documented budget.

## Gate
Green suite; `make api` serves; `web/openapi.json` generated; `docs/API.md` lists endpoints with examples.
