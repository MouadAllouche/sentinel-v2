# Phase 2 — Storage

Skills: sentinel-sqlite-patterns, sentinel-testing-workflow.

## Goal
Reliable, migrated, tested persistence for events, collector state and the audit log, with an event query API rich enough for the dashboard.

## Tasks
- `storage/database.py`: `get_connection(db_path=None)` (row_factory, `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`), `init_db(db_path=None)` applying pending migrations. Default path from settings, anchored to project root.
- `storage/migrations.py`: `MIGRATIONS = [m001, ...]`; `schema_version(version, applied_at)`; each migration idempotent and run in a transaction. This phase: `m001` creates `events`, `collector_state`, `audit_log`, `app_settings`.
- `events` table per master prompt 4.4: promoted columns populated on insert from the event (`username`, `source_ip`, `process_name`, `destination_ip`, `file_path`); indexes on `timestamp`, `event_type`, `source`, `severity`, `source_ip`, `username`, `(event_type, timestamp)`; `event_data` JSON holds the full event.
- `storage/repositories.py` (this phase): `save_event`, `save_events` (batch in one transaction), `get_event`, `get_events_by_ids`, `query_events(filters, cursor=None, limit=100)`, `count_events(filters)`, `event_time_series(filters, bucket)`, `top_values(field, filters, limit)`, `get_state/set_state`, `write_audit`, `list_audit(filters)`, `get_setting/set_setting`.
- `query_events` filters: `event_type[]`, `severity[]`, `source[]`, `username`, `source_ip`, `process_name`, `since`, `until`, `search` (substring in `description`), `allowlisted`, `incident_id` (join later). Ordering `timestamp DESC, id DESC`. **Keyset (cursor) pagination** — cursor encodes `(timestamp, id)`; never OFFSET on large tables. Returns `{items, next_cursor}`.
- `save_event(event, db_path=None, *, severity_source="default") -> int | None` returns the new id or `None` when the hash already exists (`INSERT OR IGNORE`). Raises `ValueError` for invalid or naive-timestamp events.
- Never write `event_data` that contains keys outside the normalizer's allowed set.

## Worked example
```python
init_db(tmp)
eid = save_event(make_event(), tmp)            # 1
assert save_event(make_event(), tmp) is None   # duplicate
page = query_events({"event_type": ["failed_login"], "source_ip": "203.0.113.45"}, limit=50, db_path=tmp)
page["items"][0]["id"] == eid ; page["next_cursor"] is None
```

## Tests
Migrations idempotent and re-runnable; WAL enabled; promoted columns match JSON; duplicate ignored; invalid/naive rejected; every filter; combined filters; keyset pagination across ≥250 events with equal timestamps (no duplicates, no gaps); `count_events`; time series buckets (hour/day) zero-filled option; `top_values`; state round trip; audit write/list; settings round trip; concurrent writers (two connections, no `database is locked` under `busy_timeout`); hypothesis: save/get round trip preserves the event.

## Gate
Green suite; no test touches the real DB.
