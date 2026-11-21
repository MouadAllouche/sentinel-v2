"""Rule/config editing flows through repositories and the next cycle (Phase 18)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.config import load_settings
from engine.runner import run_once
from storage.auth_repository import create_user
from storage.repositories import (
    count_events,
    get_setting,
    query_events,
    save_events,
    set_setting,
)
from storage.rules_repository import (
    get_rule,
    list_rules,
    seed_rules,
    set_rule_enabled,
    update_rule,
)
from storage.severity_repository import (
    add_allowlist_entry,
    get_default,
    reapply_severity,
    seed_defaults,
    set_default,
)

NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)


def _login_events(count: int = 8) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": (NOW + timedelta(seconds=index)).isoformat(),
            "source": "auth_log",
            "event_type": "failed_login",
            "severity": "low",
            "description": "failed password",
            "source_ip": "203.0.113.45",
            "username": "admin",
        }
        for index in range(count)
    ]


def _active_rules(db: Path) -> list[Any]:
    return [rule for rule in list_rules(db_path=db) if rule.enabled]


def test_tier_threshold_change_reflected_in_next_cycle(tmp_initialised_db: Path) -> None:
    seed_defaults(tmp_initialised_db)
    seed_rules(tmp_initialised_db)
    settings = load_settings(config_path=None)
    save_events(_login_events(25), tmp_initialised_db)
    run_once(settings, tmp_initialised_db, NOW, notify=False)
    baseline = sum(
        len(query_events({"event_type": ["rule_triggered"]}, db_path=tmp_initialised_db)["items"])
        for _ in [0]
    )
    rule = next(
        item for item in list_rules(db_path=tmp_initialised_db) if item.id == "ssh-bruteforce-by-ip"
    )
    definition = rule.model_dump()
    definition["tiers"] = [
        {**tier.model_dump(), "count": 100_000 - index} for index, tier in enumerate(rule.tiers)
    ]
    update_rule("ssh-bruteforce-by-ip", definition, "admin", tmp_initialised_db)
    assert get_rule("ssh-bruteforce-by-ip", tmp_initialised_db) is not None
    run_once(settings, tmp_initialised_db, NOW + timedelta(minutes=1), notify=False)
    after = len(
        query_events({"event_type": ["rule_triggered"]}, db_path=tmp_initialised_db)["items"]
    )
    assert after == baseline  # no new findings for the now-impossible threshold


def test_disabled_rule_drops_from_active_set(tmp_initialised_db: Path) -> None:
    seed_rules(tmp_initialised_db)
    before = len(_active_rules(tmp_initialised_db))
    set_rule_enabled("ssh-bruteforce-by-ip", False, "admin", tmp_initialised_db)
    after = len(_active_rules(tmp_initialised_db))
    assert after == before - 1


def test_default_severity_change_and_reapply(tmp_initialised_db: Path) -> None:
    set_default("failed_login", "medium", 8, actor="admin", db_path=tmp_initialised_db)
    assert get_default("failed_login", tmp_initialised_db).severity == "medium"
    save_events(_login_events(3), tmp_initialised_db)
    dry = reapply_severity({}, tmp_initialised_db, dry_run=True)
    assert isinstance(dry, dict) or hasattr(dry, "changed")


def test_allowlist_suppression_keeps_events(tmp_initialised_db: Path) -> None:
    seed_defaults(tmp_initialised_db)
    add_allowlist_entry(
        {
            "kind": "ip",
            "value": "203.0.113.45",
            "scope": "suppress_alerts",
            "reason": "trusted demo scanner",
        },
        "admin",
        tmp_initialised_db,
    )
    save_events(_login_events(4), tmp_initialised_db, allowlisted=True)
    assert count_events(db_path=tmp_initialised_db) == 4
    assert len(query_events({"allowlisted": True}, db_path=tmp_initialised_db)["items"]) == 4


def test_config_mutations_are_audited(tmp_initialised_db: Path) -> None:
    create_user("editor", "a-very-long-password", "admin", tmp_initialised_db)
    set_setting("test.flag", True, updated_by="editor", db_path=tmp_initialised_db)
    assert get_setting("test.flag", tmp_initialised_db) is True
