"""Validated rule documents.

Pydantic v2 models with path-aware errors plus non-fatal warnings for dominated
tiers. Pure: no database, clock or filesystem.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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


class ZTier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    z: float = Field(ge=0.5, le=100)
    min_absolute: int = Field(ge=1)
    severity: str
    points: int = Field(ge=0, le=100)


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
    severity: str = "low"
    points: int = 0
    tiers: list[Tier] = Field(default_factory=list)
    z_tiers: list[ZTier] = Field(default_factory=list)
    correlate_on: list[str] = Field(default_factory=list)
    within_seconds: int = 0
    steps: list[dict[str, Any]] = Field(default_factory=list)
    field: str | None = None
    per: str | None = None
    learning_days: int = 30
    min_history_events: int = 0
    metric: str | None = None
    subject: str | None = None
    min_std: float = 1.0
    window_days: int = 7
    min_samples: int = 24
    min_history_hours: int = 24
    meta_conditions: list[dict[str, Any]] = Field(default_factory=list)
    version: int = 1
    builtin: bool = False
    default_definition_json: str = ""

    @model_validator(mode="before")
    @classmethod
    def _reshape_reserved_kinds(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        reshaped = dict(data)
        if reshaped.get("kind") == "baseline_metric" and "tiers" in reshaped:
            reshaped["z_tiers"] = reshaped.pop("tiers")
        if reshaped.get("kind") == "incident_meta" and "conditions" in reshaped:
            reshaped["meta_conditions"] = reshaped.pop("conditions")
        return reshaped


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


def _validate_sequence(obj: dict[str, Any], errors: list[dict[str, str]]) -> None:
    steps = obj["steps"]
    if not 1 <= len(steps) <= 5:
        errors.append(_error("steps", "between 1 and 5 steps are required"))
    for index, step in enumerate(steps):
        match = step.get("match") or {}
        if not match.get("event_types"):
            errors.append(_error(f"steps[{index}].match.event_types", "steps need event types"))
        if not 1 <= int(step.get("min_count", 0)) <= 100_000:
            errors.append(_error(f"steps[{index}].min_count", "min_count must be 1-100000"))
        window = step.get("window_seconds")
        if window is not None and not 10 <= window <= 2_592_000:
            errors.append(_error(f"steps[{index}].window_seconds", "invalid step window"))
    if not obj["correlate_on"] or not set(obj["correlate_on"]) <= _GROUP_BY:
        errors.append(_error("correlate_on", "correlate_on needs known entity fields"))
    if not 1 <= obj["within_seconds"] <= 2_592_000:
        errors.append(_error("within_seconds", "within_seconds must be 1-2592000"))


def _validate_new_value(obj: dict[str, Any], errors: list[dict[str, str]]) -> None:
    allowed = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    field = obj.get("field")
    if not isinstance(field, str) or (field not in allowed and not field.startswith("details.")):
        errors.append(_error("field", "field must be known or a details.* path"))
    if obj.get("per") not in allowed:
        errors.append(_error("per", "per must be a known event field"))
    if not 1 <= obj["learning_days"] <= 365:
        errors.append(_error("learning_days", "learning_days must be 1-365"))
    if obj["min_history_events"] < 0:
        errors.append(_error("min_history_events", "min_history_events must be non-negative"))


def _validate_field_match(obj: dict[str, Any], errors: list[dict[str, str]]) -> None:
    if not set(obj["group_by"]) <= _GROUP_BY:
        errors.append(_error("group_by", "group_by contains an unsupported field"))
    if not 0 <= obj["cooldown_seconds"] <= 604_800:
        errors.append(_error("cooldown_seconds", "cooldown_seconds must be 0-604800"))


def _validate_reserved(obj: dict[str, Any], errors: list[dict[str, str]]) -> None:
    if obj["kind"] == "baseline_metric":
        if not obj.get("metric") or not obj.get("subject"):
            errors.append(_error("metric", "baseline_metric needs metric and subject"))
        z_tiers = obj["z_tiers"]
        if not 1 <= len(z_tiers) <= 10:
            errors.append(_error("z_tiers", "between 1 and 10 z-tiers are required"))
        z_values = [tier["z"] for tier in z_tiers]
        if z_values != sorted(z_values) or len(set(z_values)) != len(z_values):
            errors.append(_error("z_tiers", "z thresholds must strictly increase"))
        for index, tier in enumerate(z_tiers):
            if tier["severity"] not in VALID_SEVERITIES:
                errors.append(_error(f"z_tiers[{index}].severity", "invalid severity"))
        if obj["min_std"] < 0.1:
            errors.append(_error("min_std", "min_std must be at least 0.1"))
    elif obj["kind"] == "incident_meta":
        conditions = obj["meta_conditions"]
        if not 1 <= len(conditions) <= 5:
            errors.append(_error("conditions", "between 1 and 5 meta conditions are required"))
        if any(not item.get("metric") for item in conditions):
            errors.append(_error("conditions", "meta conditions need a metric"))


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
    elif rule.kind == "sequence":
        _validate_sequence(raw, validation_errors)
    elif rule.kind == "new_value":
        _validate_new_value(raw, validation_errors)
    elif rule.kind == "field_match":
        _validate_field_match(raw, validation_errors)
    elif rule.kind in {"baseline_metric", "incident_meta"}:
        _validate_reserved(raw, validation_errors)
    else:
        validation_errors.append(_error("kind", f"unknown rule kind: {rule.kind}"))
    if rule.kind in {"sequence", "new_value", "field_match", "baseline_metric", "incident_meta"}:
        if rule.severity not in VALID_SEVERITIES:
            validation_errors.append(_error("severity", "invalid severity"))
        if not 0 <= rule.points <= 100:
            validation_errors.append(_error("points", "points must be 0-100"))
    if validation_errors:
        raise RuleValidationError(validation_errors)
    return rule, _dominance_warnings(rule.tiers) if rule.kind == "threshold" else []
