# API

The FastAPI backend is the only interface the dashboard uses. It binds to `127.0.0.1:8000`
by default, requires a session cookie for everything except the minimal health check, and is
same-origin proxied by the web app. The generated OpenAPI document is committed at
`web/openapi.json`; regenerate with `make openapi`.

## Authentication and safety

- `POST /api/auth/login` with `{"username","password"}` sets `sentinel_session` (HttpOnly,
  SameSite=Strict) and `sentinel_csrf` (readable by JavaScript). No default credentials and no
  self-registration; the first admin is created interactively with
  `python cli.py user create --role admin`.
- Unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) require header `X-CSRF-Token` equal to the CSRF
  cookie, plus a matching `Origin` when present. Viewer role reads; admin role mutates.
- All JSON errors use `{"error":{"code","message","details?"}}`. Validation details carry JSON
  paths. Responses never contain password hashes, session tokens, env-var values or file contents.

## Endpoint groups

| Group | Endpoints (all under `/api`) |
|---|---|
| Auth | `POST /auth/login`, `/auth/logout`, `GET /auth/me`, `POST /auth/password`, `GET/DELETE /auth/sessions` |
| Events | `GET /events` (filters, keyset cursor, `limit ≤ 500`), `GET /events/{id}`, `/events/stats`, `/events/top`, `/events/export`, `POST /events/reapply-severity` |
| Incidents | `GET /incidents`, `/incidents/{id}`, `/timeline`, `/explanation`, `/graph`, `/notes`, `/export`; `POST /status`, `/notes`; `PATCH /incidents/{id}` |
| Rules | `GET/POST /rules`, `GET/PUT/DELETE /rules/{id}`, `/enable`, `/disable`, `/reset`, `/versions`, `/validate`, `/preview`, `/backtest`, `/findings`, `/schema` |
| Severity | `GET/PUT /severity/defaults/...`, `/reset`, `GET/POST /severity/overrides`, `PUT/DELETE /severity/overrides/{id}` |
| Allowlist | `GET/POST /allowlist`, `PUT/DELETE /allowlist/{id}` |
| Behavior/Drift | `GET /baselines`, `/baselines/series`, `/anomalies`, `/drift/paths`, `/drift/status`; admin add/reset/accept/check |
| Notifications | `GET/POST /notifications/channels`, `PUT/DELETE /notifications/channels/{id}`, `GET /notifications/log` |
| System | `GET /api/health` (minimal unauthenticated), `/api/collectors`, `/api/cycles`, `/api/system/info`; `POST /api/engine/run` (admin), retention read/dry-run/apply |
| Users/Audit/Filters | `GET/POST /users`, `PATCH /users/{id}`, `GET /audit`, `GET/POST/DELETE /filters/saved` |
| Stream | `GET /stream` — SSE, ids only, `Last-Event-ID` resume, heartbeats |

## Examples

```sh
curl -c cookies.txt -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"…"}' http://127.0.0.1:8000/api/auth/login
CSRF=$(grep sentinel_csrf cookies.txt | awk '{print $7}')
curl -b cookies.txt -H "X-CSRF-Token: $CSRF" http://127.0.0.1:8000/api/events?limit=50
```

Rule creation posts a validated JSON document (see `docs/RULES.md`); invalid documents return 422
with a `details` array of `{path, message}` entries the UI maps to form fields. Backtest and export
endpoints are bounded by range/row caps and return a clear 4xx when exceeded.

## Complete endpoint catalogue
Generated from `web/openapi.json`; every path below is served by the FastAPI app.
- `/api/allowlist` — GET, POST
- `/api/allowlist/stats` — GET
- `/api/allowlist/{identifier}` — DELETE, PUT
- `/api/anomalies` — GET
- `/api/audit` — GET
- `/api/auth/login` — POST
- `/api/auth/logout` — POST
- `/api/auth/me` — GET
- `/api/auth/password` — POST
- `/api/auth/sessions` — GET
- `/api/auth/sessions/{identifier}` — DELETE
- `/api/baselines` — GET
- `/api/baselines/series` — GET
- `/api/changes` — GET
- `/api/collectors` — GET
- `/api/cycles` — GET
- `/api/drift/accept` — POST
- `/api/drift/check` — POST
- `/api/drift/paths` — GET, POST
- `/api/drift/paths/{identifier}` — DELETE, PUT
- `/api/drift/paths/{identifier}/history` — GET
- `/api/drift/paths/{identifier}/reset` — POST
- `/api/drift/status` — GET
- `/api/engine/run` — POST
- `/api/events` — GET
- `/api/events/export` — GET
- `/api/events/reapply-severity` — POST
- `/api/events/stats` — GET
- `/api/events/top` — GET
- `/api/events/{event_id}` — GET
- `/api/filters/saved` — GET, POST
- `/api/filters/saved/{identifier}` — DELETE
- `/api/health` — GET
- `/api/incidents` — GET
- `/api/incidents/bulk-status` — POST
- `/api/incidents/{identifier}` — GET, PATCH
- `/api/incidents/{identifier}/explanation` — GET
- `/api/incidents/{identifier}/export` — GET
- `/api/incidents/{identifier}/graph` — GET
- `/api/incidents/{identifier}/history` — GET
- `/api/incidents/{identifier}/notes` — GET, POST
- `/api/incidents/{identifier}/status` — POST
- `/api/incidents/{identifier}/timeline` — GET
- `/api/notifications/channels` — GET, POST
- `/api/notifications/channels/{identifier}` — DELETE, PUT
- `/api/notifications/channels/{identifier}/test` — POST
- `/api/notifications/log` — GET
- `/api/retention/apply` — POST
- `/api/retention/dry-run` — POST
- `/api/risk/decay` — GET, PUT
- `/api/risk/thresholds` — GET, PUT
- `/api/rules` — GET, POST
- `/api/rules/export` — GET
- `/api/rules/findings` — GET
- `/api/rules/import` — POST
- `/api/rules/preview` — POST
- `/api/rules/schema` — GET
- `/api/rules/validate` — POST
- `/api/rules/{identifier}` — DELETE, GET, PUT
- `/api/rules/{identifier}/backtest` — POST
- `/api/rules/{identifier}/disable` — POST
- `/api/rules/{identifier}/enable` — POST
- `/api/rules/{identifier}/reset` — POST
- `/api/rules/{identifier}/versions` — GET
- `/api/rules/{identifier}/versions/{version}/restore` — POST
- `/api/settings/retention` — GET, PUT
- `/api/severity/defaults` — GET
- `/api/severity/defaults/reset` — POST
- `/api/severity/defaults/{event_type}` — PUT
- `/api/severity/defaults/{event_type}/reset` — POST
- `/api/severity/overrides` — GET, POST
- `/api/severity/overrides/reorder` — POST
- `/api/severity/overrides/test` — POST
- `/api/severity/overrides/{identifier}` — DELETE, PUT
- `/api/severity/overrides/{identifier}/reset` — POST
- `/api/stream` — GET
- `/api/system/info` — GET
- `/api/users` — GET, POST
- `/api/users/{identifier}` — PATCH
- `/api/users/{identifier}/password-reset` — POST
- `/api/users/{identifier}/sessions/revoke` — POST
