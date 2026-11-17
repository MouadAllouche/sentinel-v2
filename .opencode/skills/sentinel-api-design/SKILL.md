---
name: sentinel-api-design
description: Conventions for Sentinel's FastAPI backend - app factory, routers, schemas, errors, pagination, filters, SSE, OpenAPI contract, testing with TestClient. Load when writing or changing anything under api/, or frontend code that consumes the API.
---

# API design

- `create_app(settings=None, db_path=None)` factory; routers in `api/routers/*.py` under `/api`; thin handlers: validate → call `core`/`storage` → serialize. No business logic or SQL in routers.
- Pydantic v2 models for every request/response; `extra="forbid"` on requests; `response_model` everywhere; ISO-8601 UTC strings; ids: ints (events/incidents), slugs (rules).
- Errors: `{"error": {"code": "forbidden|csrf_failed|validation_error|not_found|conflict|rate_limited|…", "message": str, "details": [{"path": "tiers[1].count", "message": "..."}]}}`. Validation errors carry JSON paths so the UI can map them to fields. Use 409 for concurrent-edit conflicts (`updated_at` check).
- Pagination: keyset cursors `{items, next_cursor}`; `limit` default 50, max 500. Filters are explicit query params; lists as repeated params.
- Auth deps: `current_user`, `require_role("admin")`; unsafe methods require CSRF header (see security skill). Rate-limit expensive endpoints (backtest, export, reapply, engine run).
- Long work (backtest, export) bounded by range/row caps and time limits; return 4xx with a clear message when exceeded.
- SSE `/api/stream`: `text/event-stream`, heartbeats 15 s, ids only (client refetches), `Last-Event-ID` resume from `changes`, per-user connection cap, cleanup on disconnect, no buffering.
- OpenAPI is the contract: generated file committed at `web/openapi.json`; a test fails if stale; the frontend types are generated from it — never hand-write duplicate response types.
- Mutations: single transaction including the audit row; return the updated resource; idempotent where possible (PUT).
- Responses never include password hashes, session tokens, env-var values, or file contents.
- Tests: `TestClient` + tmp DB; parametrise RBAC over every non-GET route from the OpenAPI schema; assert audit rows for every mutation; no network.
