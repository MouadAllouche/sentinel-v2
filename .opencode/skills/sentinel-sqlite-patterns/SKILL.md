---
name: sentinel-sqlite-patterns
description: SQLite conventions for Sentinel - connections, WAL, migrations, repositories, keyset pagination, JSON columns, idempotent upserts, retention, and test isolation. Load when writing storage code, migrations, queries or repository functions.
---

# SQLite patterns

- Connection: `sqlite3.connect(path, timeout=5)`, `row_factory=sqlite3.Row`, `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`. Read-only API paths may use `file:...?mode=ro` URIs.
- Transactions: `with closing(conn): with conn:` (commit/rollback). Batch writes in one transaction. Keep write transactions short; never hold one across network or sleep.
- **Parameterised SQL only.** Never f-string values; dynamic column/ORDER names come from whitelists. A test statically scans `storage/` for f-strings inside `execute`.
- Migrations: `schema_version` table + ordered list of idempotent functions; each phase appends exactly one; never edit an applied migration — add a new one. Test: running twice is a no-op; applying to a v-1 DB upgrades.
- JSON: store full documents as TEXT JSON plus **promoted indexed columns** for fields you filter on. Use `json_extract` only for rare filters. Always `json.dumps(sort_keys=True, default=str)`.
- Idempotence: unique keys + `INSERT OR IGNORE` (events by `event_hash`, findings by `(rule_id, group_key, tier_index, window_start)`, risk assessments by `(target_type,target_id)` with `ON CONFLICT DO UPDATE`). Functions return whether a row was new.
- **Keyset pagination** `(timestamp, id)` encoded in an opaque cursor; never OFFSET on large tables. Filters build `WHERE` from a whitelist of conditions.
- Indexes follow queries: `(event_type, timestamp)`, `timestamp`, `source_ip`, `username`, `severity`. Check with `EXPLAIN QUERY PLAN` in tests for hot queries.
- Seeding: insert-missing-only; never overwrite user edits; keep `default_*` columns for reset.
- Soft delete (`deleted_at`) for entities referenced elsewhere (rules).
- Audit: every config mutation writes `audit_log(actor, action, target, before_json, after_json)` in the **same transaction** as the change.
- Retention: delete in chunks (e.g. 5 000 rows) with `LIMIT` subselects; never delete evidence linked to open incidents.
- Every function takes `db_path=None`. Tests use `tmp_path` only.
