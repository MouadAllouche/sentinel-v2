# Phase 1 — Events and normalization

Skills: sentinel-event-schema, sentinel-testing-workflow.

## Goal
A pure, fully tested definition of what an event is, how raw collector output becomes one, and the event taxonomy used by every later phase.

## Tasks
- `core/events.py`: constants `REQUIRED_FIELDS`, `OPTIONAL_FIELDS`, `VALID_SEVERITIES`, `EVENT_TYPES`, `SOURCES`; `validate_event(event) -> bool` per master prompt 4.1. Also `SEVERITY_ORDER = {"low":0,"medium":1,"high":2,"critical":3}` and helpers `max_severity(a, b)`, `severity_at_least(a, b)`.
- `core/normalizer.py`: `normalize_event(raw) -> dict` (raises `ValueError` on non-dict or invalid result). Copies only known fields, resolves aliases, maps event-type aliases, converts timestamps to UTC-aware ISO, strips whitespace from text fields, drops empty-string optionals, leaves `details` untouched (dict required). `canonicalize(event) -> str` and `compute_event_hash(event) -> str` (excluding `severity`, `severity_source`, `enrichment`).
- A `NormalizedEvent` `TypedDict` for typing only.

## Worked examples
```python
normalize_event({"time": "2026-11-15 10:00:00", "action": "login_failure", "level": "medium",
                 "message": "Failed SSH login attempt for admin", "user": "admin", "ip": "203.0.113.45",
                 "source_system": "auth_log", "junk": 1})
# -> {"timestamp": "2026-11-15T10:00:00+00:00" (if server TZ is UTC), "source": "auth_log",
#     "event_type": "failed_login", "severity": "medium", "description": "...",
#     "username": "admin", "source_ip": "203.0.113.45"}      # "junk" dropped

compute_event_hash(e1) == compute_event_hash({**e1, "severity": "high"})        # True  (severity excluded)
compute_event_hash(e1) == compute_event_hash({**e1, "enrichment": {"x": 1}})    # True
compute_event_hash(e1) == compute_event_hash({**e1, "username": "root"})        # False
```

## Tests (minimum)
Valid event; missing each required field; invalid severity; invalid timestamp; empty strings; every type check (`destination_port`, `process_id`, `details`, `enrichment`, `user_permissions` shapes); every alias; event-type aliases; naive→UTC conversion; unknown fields dropped; network fields preserved (`local_ip`, `destination_ip`, `destination_port`, `connection_status`, `process_id`); `pytest.raises` for invalid; hash stability under key order; hash exclusions; `SEVERITY_ORDER` helpers incl. boundaries; property test (hypothesis): `normalize_event(normalize_event(x)) == normalize_event(x)` for generated valid events.

## Gate
Suite green; `mypy` strict passes on `core/events.py`, `core/normalizer.py`.
