"""Pure rule dispatch. Reserved kinds are reported, never silently skipped."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.rules.field_match import evaluate_field_match
from core.rules.models import Rule
from core.rules.new_value import ValueHistory, evaluate_new_value
from core.rules.sequence import evaluate_sequence
from core.rules.threshold import Finding, evaluate_threshold

__all__ = ["evaluate_rules"]


def evaluate_rules(
    rules: list[Rule],
    events: list[dict[str, Any]],
    now: datetime,
    history: dict[str, dict[str, ValueHistory]] | None = None,
) -> tuple[list[Finding], list[str]]:
    """Evaluate implemented kinds; return findings plus explicit warnings."""
    findings: list[Finding] = []
    warnings: list[str] = []
    for rule in rules:
        if rule.kind == "threshold":
            findings.extend(evaluate_threshold(rule, events, now))
        elif rule.kind == "sequence":
            findings.extend(evaluate_sequence(rule, events, now))
        elif rule.kind == "new_value":
            findings.extend(evaluate_new_value(rule, events, (history or {}).get(rule.id, {}), now))
        elif rule.kind == "field_match":
            findings.extend(evaluate_field_match(rule, events, now))
        else:
            warnings.append(
                f"rule '{rule.id}' has kind '{rule.kind}': NotImplementedForKind "
                "(evaluated in a later phase)"
            )
    return findings, warnings
