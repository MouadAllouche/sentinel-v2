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
| System | `GET /health` (minimal unauthenticated), `/collectors`, `/cycles`, `/system/info`; `POST /engine/run` (admin), retention read/dry-run/apply |
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
