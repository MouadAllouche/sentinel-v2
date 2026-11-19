"""Validated rule documents.

Pydantic v2 models with path-aware errors plus non-fatal warnings for dominated
tiers. Pure: no database, clock or filesystem.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.conditions import validate_condition
from core.events import (
    EVENT_TYPES,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    SEVERITY_ORDER,
    VALID_SEVERITIES,
)

__all__ = ["Rule", "RuleValidationError", "Tier", "validate_rule"]

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_GROUP_BY = frozenset(
    {"source_ip", "username", "process_name", "destination_ip", "file_path", "source"}
)
_ALIGNMENT_SECONDS = {"minute": 60, "hour": 3600, "day": 86400}
_RESERVED_KINDS = frozenset(
    {"sequence", "new_value", "field_match", "baseline_metric", "incident_meta"}
)
_KNOWN_KINDS = frozenset({"threshold", *_RESERVED_KINDS})


class RuleValidationError(ValueError):
    """A validated rule document with structured, path-aware errors."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        self.errors = errors
        super().__init__(json.dumps(errors, sort_keys=True))


class Tier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    count: int = Field(ge=1, le=100_000)
    window_seconds: int = Field(ge=10, le=2_592_000)
    severity: str
    points: int = Field(ge=0, le=100)


class Aggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "count"
    field: str | None = None


class Match(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_types: list[str] = Field(default_factory=list)
    conditions: Any = None


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exclude_allowlisted: bool = True


class Actions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    create_incident: bool = True
    notify: bool = True
    tags: list[str] = Field(default_factory=list)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    kind: str
    enabled: bool = True
    match: Match
    scope: Scope = Field(default_factory=Scope)
    actions: Actions = Field(default_factory=Actions)
    mitre: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregate: Aggregate = Field(default_factory=Aggregate)
    window_mode: str = "sliding"
    fixed_alignment: str | None = None
    cooldown_seconds: int = 0
    tiers: list[Tier] = Field(default_factory=list)
    version: int = 1
    builtin: bool = False
    default_definition_json: str = ""


def _error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def _validate_definition(obj: dict[str, Any], errors: list[dict[str, str]]) -> None:
    if not _SLUG.match(obj["id"]):
        errors.append(_error("id", "id must be a 3-64 character lowercase slug"))
    if not 3 <= len(obj["name"]) <= 80:
        errors.append(_error("name", "name must be 3-80 characters"))
    if len(obj["description"]) > 500:
        errors.append(_error("description", "description must be at most 500 characters"))
    event_types = obj["match"].get("event_types") or []
    if not event_types or not set(event_types) <= set(EVENT_TYPES):
        errors.append(_error("match.event_types", "event_types must be a non-empty known list"))
    detection = sorted({"rule_triggered", "anomaly"} & set(event_types))
    if detection:
        errors.append(_error("match.event_types", f"{', '.join(detection)} cannot be matched here"))
    if obj["match"].get("conditions") is not None:
        try:
            validate_condition(obj["match"]["conditions"])
        except ValueError as exc:
            errors.append(_error("match.conditions", str(exc)))
    if not 0 <= obj["cooldown_seconds"] <= 604_800:
        errors.append(_error("cooldown_seconds", "cooldown_seconds must be 0-604800"))


def _validate_threshold(obj: dict[str, Any], errors: list[dict[str, str]]) -> None:
    if not set(obj["group_by"]) <= _GROUP_BY:
        errors.append(_error("group_by", "group_by contains an unsupported field"))
    tiers = obj["tiers"]
    if not 1 <= len(tiers) <= 10:
        errors.append(_error("tiers", "between 1 and 10 tiers are required"))
    if len({tier["label"] for tier in tiers}) != len(tiers):
        errors.append(_error("tiers.label", "tier labels must be unique"))
    if len({(tier["count"], tier["window_seconds"]) for tier in tiers}) != len(tiers):
        errors.append(_error("tiers", "tier (count, window_seconds) pairs must be unique"))
    for index, tier in enumerate(tiers):
        if tier["severity"] not in VALID_SEVERITIES:
            errors.append(_error(f"tiers[{index}].severity", "invalid severity"))
    if obj["aggregate"].get("type") == "distinct_count":
        field = obj["aggregate"].get("field")
        allowed = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
        if not isinstance(field, str) or (
            field not in allowed and not field.startswith("details.")
        ):
            errors.append(
                _error("aggregate.field", "distinct_count needs a known field or details.* path")
            )
    elif obj["aggregate"].get("type") not in {"count", "distinct_count"}:
        errors.append(_error("aggregate.type", "aggregate type must be count or distinct_count"))
    if obj["window_mode"] not in {"sliding", "fixed"}:
        errors.append(_error("window_mode", "window_mode must be sliding or fixed"))
    if obj["window_mode"] == "fixed":
        alignment = obj.get("fixed_alignment")
        if alignment not in _ALIGNMENT_SECONDS:
            errors.append(
                _error("fixed_alignment", "fixed mode requires minute/hour/day alignment")
            )
        else:
            for index, tier in enumerate(tiers):
                if tier["window_seconds"] != _ALIGNMENT_SECONDS[alignment]:
                    errors.append(
                        _error(
                            f"tiers[{index}].window_seconds",
                            "fixed windows must equal the alignment length",
                        )
                    )


def _dominance_warnings(tiers: list[Tier]) -> list[str]:
    warnings: list[str] = []
    for index, tier in enumerate(tiers):
        for other in tiers[index + 1 :]:
            if (
                other.count >= tier.count
                and other.window_seconds >= tier.window_seconds
                and SEVERITY_ORDER[other.severity] <= SEVERITY_ORDER[tier.severity]
            ):
                warnings.append(
                    f"tier '{other.label}' dominates '{tier.label}' "
                    "(larger-or-equal count and window with lower-or-equal severity)"
                )
    return warnings


def validate_rule(obj: object) -> tuple[Rule, list[str]]:
    """Validate a rule document; returns the model and non-fatal warnings."""
    if not isinstance(obj, dict):
        raise RuleValidationError([_error("rule", "rule must be an object")])
    try:
        rule = Rule.model_validate(obj)
    except ValidationError as exc:
        errors = [
            _error(".".join(str(part) for part in item["loc"]), item["msg"])
            for item in exc.errors()
        ]
        raise RuleValidationError(errors) from exc
    validation_errors: list[dict[str, str]] = []
    raw = rule.model_dump()
    _validate_definition(raw, validation_errors)
    if rule.kind == "threshold":
        _validate_threshold(raw, validation_errors)
    elif rule.kind not in _KNOWN_KINDS:
        validation_errors.append(_error("kind", f"unknown rule kind: {rule.kind}"))
    if validation_errors:
        raise RuleValidationError(validation_errors)
    return rule, _dominance_warnings(rule.tiers) if rule.kind == "threshold" else []
