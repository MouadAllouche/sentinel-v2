"""The generic rule cycle must not warn about kinds handled in other stages."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.rules.defaults import DEFAULT_RULES
from core.rules.engine import evaluate_rules
from core.rules.models import validate_rule

FORBIDDEN = ("evaluated by the baseline cycle", "NotImplementedForKind", "later phase")


def _seeded_rules(kinds: set[str]) -> list[Any]:
    return [
        validate_rule(definition)[0] for definition in DEFAULT_RULES if definition["kind"] in kinds
    ]


def test_evaluate_rules_is_silent_for_kinds_handled_by_other_stages() -> None:
    rules = _seeded_rules({"baseline_metric", "incident_meta"})
    assert rules, "seeded defaults should include kinds handled by other stages"
    findings, warnings = evaluate_rules(rules, [], now=datetime(2026, 11, 15, 12, tzinfo=UTC))
    assert findings == []
    assert warnings == []


def test_evaluate_rules_still_warns_for_a_kind_with_no_evaluator() -> None:
    rule = validate_rule(
        next(definition for definition in DEFAULT_RULES if definition["kind"] == "threshold")
    )[0]
    unknown = rule.model_copy(update={"kind": "no_such_kind"})
    findings, warnings = evaluate_rules([unknown], [], now=datetime(2026, 11, 15, 12, tzinfo=UTC))
    assert findings == []
    assert len(warnings) == 1
    assert "no_such_kind" in warnings[0]
    assert "no evaluator" in warnings[0]
    assert not any(phrase in warnings[0] for phrase in FORBIDDEN)


def test_normal_cycle_on_seeded_rules_emits_no_stage_warnings(
    tmp_initialised_db: Path, caplog: Any
) -> None:
    from engine.rules import run_rules
    from storage.rules_repository import seed_rules

    seed_rules(tmp_initialised_db)
    with caplog.at_level(logging.WARNING):
        report = run_rules(tmp_initialised_db, now=datetime(2026, 11, 15, 12, tzinfo=UTC))
    assert report.rules_evaluated > 0
    assert [
        message for message in caplog.messages if any(phrase in message for phrase in FORBIDDEN)
    ] == []


def test_simulate_run_one_scenario_prints_no_stage_warnings(
    sim_workdir: Path, capsys: Any, caplog: Any
) -> None:
    from cli import main

    with caplog.at_level(logging.WARNING):
        assert (
            main(
                [
                    "simulate",
                    "run",
                    "ssh-bruteforce-single-ip",
                    "--seed",
                    "7",
                    "--out",
                    str(sim_workdir / "warn-check"),
                ]
            )
            == 0
        )
    printed = capsys.readouterr().out + capsys.readouterr().err
    assert [phrase for phrase in FORBIDDEN if phrase in printed] == []
    assert [
        message for message in caplog.messages if any(phrase in message for phrase in FORBIDDEN)
    ] == []
