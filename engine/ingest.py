"""Collection orchestration.

Each enabled collector is isolated: one failure is logged and recorded but never
stops the others. State is persisted only after the events have been saved.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from collectors import CollectionResult
from collectors.dpkg import collect_dpkg_events
from collectors.journald import collect_journald_events
from collectors.listening import collect_listening_events
from collectors.logs import collect_auth_events, state_key
from collectors.network import collect_network_events
from collectors.processes import collect_process_events
from collectors.system import collect_system_info
from core.allowlist import Entry, reduce_severity
from core.allowlist import matches as allowlist_matches
from core.config import Settings
from core.enrichment import enrich_event
from core.normalizer import normalize_event
from core.severity import Override, TypeDefault, resolve_severity
from core.timeutil import floor_hour, utc_now
from storage.database import init_db
from storage.repositories import get_state, record_collector_run, save_events, set_state
from storage.severity_repository import (
    get_allowlist_entries,
    get_defaults,
    get_overrides,
    seed_defaults,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestReport:
    events_found: int = 0
    events_new: int = 0
    runs: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _apply_pipeline(
    event: dict[str, Any],
    defaults: dict[str, TypeDefault],
    overrides: list[Override],
    entries: list[Entry],
    now: datetime,
) -> tuple[dict[str, Any], bool] | None:
    """Enrich, annotate, resolve severity; return None for disabled types.

    The second element of the result is the ``allowlisted`` storage flag.
    """
    default = defaults.get(str(event.get("event_type")))
    if default is not None and not default.enabled:
        return None
    enriched = enrich_event(event)
    matched = allowlist_matches(enriched, entries, now)
    enriched["enrichment"]["allowlist_match"] = [str(entry.id) for entry in matched]
    severity, source = resolve_severity(enriched, defaults, overrides)
    lowering = next((entry for entry in matched if entry.scope == "lower_severity"), None)
    if lowering is not None:
        severity = reduce_severity(severity)
        source = f"allowlist:{lowering.id}"
    enriched["severity"] = severity
    enriched["severity_source"] = source
    return enriched, bool(matched)


def _collector_specs(
    settings: Settings, now: datetime
) -> list[tuple[str, str, Callable[..., CollectionResult]]]:
    specs: list[tuple[str, str, Callable[..., CollectionResult]]] = []
    collectors = settings.collectors
    if collectors.auth_source in {"auth_log", "both"}:
        path = str(settings.paths.auth_log)
        specs.append(
            (
                "auth_log",
                state_key(path),
                lambda state, path=path: collect_auth_events(path, state, now=now),
            )
        )
    if collectors.auth_source in {"journald", "both"}:
        unit = collectors.journald_unit
        specs.append(
            (
                "journald",
                f"journald:{unit}",
                lambda state, unit=unit: collect_journald_events(unit, state, now=now),
            )
        )
    if collectors.dpkg:
        specs.append(
            (
                "dpkg",
                "dpkg:" + str(settings.paths.dpkg_log),
                lambda state: collect_dpkg_events(settings.paths.dpkg_log, state, now=now),
            )
        )
    if collectors.network:
        specs.append(
            ("network", "network:state", lambda state: collect_network_events(state, now=now))
        )
    if collectors.listening:
        specs.append(
            ("listening", "listening:state", lambda state: collect_listening_events(state, now=now))
        )
    if collectors.processes:
        specs.append(
            (
                "processes",
                "processes:state",
                lambda state: collect_process_events(
                    state, now=now, max_events=collectors.max_process_events_per_run
                ),
            )
        )
    if collectors.system:
        current_hour = floor_hour(now).isoformat()

        def collect_system(
            state: dict[str, Any], current_hour: str = current_hour
        ) -> CollectionResult:
            if (state or {}).get("last_hour") == current_hour:
                return CollectionResult()
            return CollectionResult(
                events=[collect_system_info(now=now)],
                warnings=[],
                state={"last_hour": current_hour},
            )

        specs.append(("system", "system:hour", collect_system))
    return specs


def run_collection(
    settings: Settings,
    db_path: str | Path | None = None,
    now: datetime | None = None,
) -> IngestReport:
    """Run every enabled collector once; returns counts and per-collector runs."""
    reference = now or utc_now()
    init_db(db_path)
    seed_defaults(db_path)
    defaults = get_defaults(db_path)
    overrides = get_overrides(db_path)
    entries = get_allowlist_entries(db_path)
    report = IngestReport()

    for name, key, collect in _collector_specs(settings, reference):
        started_at = reference.isoformat()
        state = get_state(key, db_path)
        events_found = 0
        new_count = 0
        message: str | None = None
        try:
            result = collect(state)
            events_found = len(result.events)
            prepared: list[tuple[dict[str, Any], bool]] = []
            skipped: list[str] = []
            for raw_event in result.events:
                normalised = normalize_event(raw_event)
                processed = _apply_pipeline(normalised, defaults, overrides, entries, reference)
                if processed is None:
                    skipped.append(str(normalised["event_type"]))
                    continue
                prepared.append(processed)
            ordinary = [event for event, flag in prepared if not flag]
            allowlisted = [event for event, flag in prepared if flag]
            identifiers = save_events(ordinary, db_path) + save_events(
                allowlisted, db_path, allowlisted=True
            )
            new_count = sum(identifier is not None for identifier in identifiers)
            if result.state is not None:
                set_state(key, result.state, db_path)
            warnings = list(result.warnings)
            if skipped:
                warnings.append(
                    "disabled event types not stored: " + ", ".join(sorted(set(skipped)))
                )
            status = "ok"
            message = "; ".join(warnings)
            report.events_found += events_found
            report.events_new += new_count
            report.warnings.extend(f"{name}: {warning}" for warning in warnings)
        except Exception as exc:  # noqa: BLE001 - one collector must never stop the others
            logger.exception("collector %s failed", name)
            status = "error"
            message = f"{type(exc).__name__}: {exc}"
            report.warnings.append(f"{name}: {message}")
        record_collector_run(
            name,
            started_at,
            finished_at=reference.isoformat(),
            events_found=events_found,
            events_new=new_count,
            status=status,
            message=message or None,
            db_path=db_path,
        )
        report.runs.append({"collector": name, "status": status, "events_new": new_count})
    return report
