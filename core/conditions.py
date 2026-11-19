"""Pure condition DSL shared by severity overrides and rules.

Untrusted condition documents are validated before evaluation: bounded nesting,
bounded lists, compiled regexes with a nested-quantifier heuristic, and no
network or environment access.
"""

from __future__ import annotations

import ipaddress
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Condition", "describe", "evaluate", "validate_condition"]

OPS = frozenset(
    {
        "eq",
        "ne",
        "in",
        "not_in",
        "contains",
        "not_contains",
        "startswith",
        "endswith",
        "regex",
        "gt",
        "gte",
        "lt",
        "lte",
        "exists",
        "not_exists",
        "cidr_in",
        "cidr_not_in",
    }
)
MAX_DEPTH = 4
MAX_LIST_ITEMS = 500
MAX_REGEX_LENGTH = 200
MAX_UNBOUNDED_QUANTIFIERS = 2
_REGEX_EVAL_LIMIT = 500


def _has_nested_quantifier(pattern: str) -> bool:
    """Reject quantifiers applied to a group that is itself quantified/alternating."""
    openings: list[int] = []
    for index, char in enumerate(pattern):
        if char == "(":
            openings.append(index)
        elif char == ")" and openings:
            start = openings.pop()
            inner = pattern[start + 1 : index]
            quantified = "|" in inner or "+" in inner or "*" in inner or re.search(r"\{\d", inner)
            followed = index + 1 < len(pattern) and pattern[index + 1] in "+*{"
            if quantified and followed:
                return True
    return False


def _unbounded_quantifiers(pattern: str) -> int:
    """Count `*`/`+`/`{n,}` outside escapes and character classes."""
    count = 0
    in_class = False
    escaped = False
    for index, char in enumerate(pattern):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "[":
            in_class = True
            continue
        if char == "]":
            in_class = False
            continue
        if in_class:
            continue
        if char in "*+" or char == "{" and re.match(r"\{\d+,", pattern[index:]):
            count += 1
    return count


_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_MISSING = object()
_REGEX_CACHE: dict[str, re.Pattern[str]] = {}
MAX_REGEX_CACHE = 128

_OP_TEXT = {
    "eq": "is",
    "ne": "is not",
    "in": "in",
    "not_in": "not in",
    "contains": "contains",
    "not_contains": "does not contain",
    "startswith": "starts with",
    "endswith": "ends with",
    "regex": "matches",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "exists": "exists",
    "not_exists": "does not exist",
    "cidr_in": "in",
    "cidr_not_in": "not in",
}


class Condition(BaseModel):
    """A leaf condition or a nested all/any/not group."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    field: str | None = None
    op: str | None = None
    value: Any = None
    ci: bool = False
    all: list[Condition] | None = None
    any: list[Condition] | None = None
    not_: Condition | None = Field(default=None, alias="not")


Condition.model_rebuild()


def _validate_regex(pattern: str, path: str) -> None:
    if len(pattern) > MAX_REGEX_LENGTH:
        raise ValueError(f"{path}: regex pattern exceeds {MAX_REGEX_LENGTH} characters")
    if _has_nested_quantifier(pattern):
        raise ValueError(f"{path}: regex pattern contains a nested quantifier")
    if _unbounded_quantifiers(pattern) > MAX_UNBOUNDED_QUANTIFIERS:
        raise ValueError(f"{path}: regex pattern has too many unbounded quantifiers")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"{path}: invalid regex: {exc}") from exc


def _validate_raw(obj: object, path: str, depth: int) -> None:
    if depth > MAX_DEPTH:
        raise ValueError(f"condition depth exceeds {MAX_DEPTH} at {path}")
    if not isinstance(obj, dict):
        raise ValueError(f"{path}: condition must be an object")
    unknown = set(obj) - {"field", "op", "value", "ci", "all", "any", "not"}
    if unknown:
        raise ValueError(f"{path}: unknown condition keys: {', '.join(sorted(unknown))}")
    groups = [key for key in ("all", "any", "not") if obj.get(key) is not None]
    if len(groups) > 1:
        raise ValueError(f"{path}: only one of all/any/not is allowed")
    if groups:
        key = groups[0]
        children = obj[key]
        if key == "not":
            _validate_raw(children, f"{path}.not", depth + 1)
        else:
            if not isinstance(children, list):
                raise ValueError(f"{path}.{key}: must be a list")
            for index, child in enumerate(children):
                _validate_raw(child, f"{path}.{key}[{index}]", depth + 1)
        return
    if not obj:
        return
    field = obj.get("field")
    op = obj.get("op")
    if not isinstance(field, str) or not _FIELD_PATTERN.match(field):
        raise ValueError(f"{path}: invalid field")
    if op not in OPS:
        raise ValueError(f"{path}: invalid op {op!r}")
    value = obj.get("value")
    if op in {"in", "not_in", "cidr_in", "cidr_not_in"}:
        if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
            raise ValueError(f"{path}: {op} requires a list of at most {MAX_LIST_ITEMS} items")
        if op in {"cidr_in", "cidr_not_in"} and not all(isinstance(item, str) for item in value):
            raise ValueError(f"{path}: {op} requires CIDR strings")
    if op == "regex":
        if not isinstance(value, str):
            raise ValueError(f"{path}: regex requires a string pattern")
        _validate_regex(value, path)


def validate_condition(obj: object) -> Condition:
    """Validate and return a condition; raises ValueError with a path-aware message."""
    _validate_raw(obj, "condition", 1)
    try:
        return Condition.model_validate(obj)
    except ValueError as exc:
        raise ValueError(f"invalid condition: {exc}") from exc


def _get_field(event: Any, path: str) -> Any:
    current: Any = event
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _text(value: Any, ci: bool) -> str:
    text = str(value)
    return text.lower() if ci else text


def _compare(left: Any, right: Any, op: str, ci: bool) -> bool:
    if op in {"in", "not_in"}:
        options = right if isinstance(right, list) else [right]
        if ci and isinstance(left, str):
            result = any(
                isinstance(item, str) and _text(left, True) == _text(item, True) for item in options
            )
        else:
            result = any(left == item for item in options)
        return not result if op == "not_in" else result
    if op in {"eq", "ne"}:
        if isinstance(left, str) and isinstance(right, str) and ci:
            result = _text(left, ci) == _text(right, ci)
        else:
            result = left == right
        return not result if op == "ne" else result
    if op in {"contains", "not_contains"}:
        if isinstance(left, str):
            result = _text(right, ci) in _text(left, ci)
        elif isinstance(left, list):
            result = any(item == right for item in left)
        else:
            result = False
        return not result if op == "not_contains" else result
    if op in {"startswith", "endswith"}:
        if not isinstance(left, str):
            return False
        haystack, needle = _text(left, ci), _text(right, ci)
        return haystack.startswith(needle) if op == "startswith" else haystack.endswith(needle)
    if op == "regex":
        pattern = _REGEX_CACHE.get(str(right))
        if pattern is None:
            pattern = re.compile(str(right))
            if len(_REGEX_CACHE) >= MAX_REGEX_CACHE:
                _REGEX_CACHE.pop(next(iter(_REGEX_CACHE)))
            _REGEX_CACHE[str(right)] = pattern
        return pattern.search(str(left)[:_REGEX_EVAL_LIMIT]) is not None
    if op in {"gt", "gte", "lt", "lte"}:
        if isinstance(left, bool) or isinstance(right, bool):
            return False
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            return False
        return {
            "gt": left > right,
            "gte": left >= right,
            "lt": left < right,
            "lte": left <= right,
        }[op]
    return False


def _cidr_match(value: Any, networks: list[Any], *, invert: bool) -> bool:
    try:
        address = ipaddress.ip_address(str(value))
    except ValueError:
        return False
    result = any(address in network for network in networks)
    return not result if invert else result


def evaluate(cond: Condition, event: Any) -> bool:
    """Return whether a condition holds for ``event``; missing fields are false."""
    if cond.all is not None:
        return all(evaluate(child, event) for child in cond.all)
    if cond.any is not None:
        return any(evaluate(child, event) for child in cond.any)
    if cond.not_ is not None:
        return not evaluate(cond.not_, event)
    if cond.field is None or cond.op is None:
        return True
    value = _get_field(event, cond.field)
    if value is _MISSING:
        return cond.op == "not_exists"
    if cond.op == "exists":
        return True
    if cond.op == "not_exists":
        return False
    if cond.op in {"cidr_in", "cidr_not_in"}:
        networks: list[Any] = []
        for item in cond.value or []:
            try:
                networks.append(ipaddress.ip_network(str(item), strict=False))
            except ValueError:
                continue
        return _cidr_match(value, networks, invert=cond.op == "cidr_not_in")
    return _compare(value, cond.value, cond.op, cond.ci)


def describe(cond: Condition) -> str:
    """Return plain-language text for UI and explanations."""
    if cond.all is not None:
        return " AND ".join(describe(child) for child in cond.all)
    if cond.any is not None:
        return " OR ".join(describe(child) for child in cond.any)
    if cond.not_ is not None:
        return f"NOT ({describe(cond.not_)})"
    if cond.field is None or cond.op is None:
        return "always true"
    rendered = json.dumps(cond.value, default=str) if cond.value is not None else ""
    return f"{cond.field} {_OP_TEXT.get(cond.op, cond.op)} {rendered}".strip()
