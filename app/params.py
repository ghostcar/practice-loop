"""Typed parameter DSL (ADR-041).

Formalizes ``Entity.params_schema`` into a structured definition list and
validates ``planned_parameters`` / ``actual_parameters`` against it.

Two accepted schema shapes (both normalized to the same internal form):

1. Legacy compact map (existing seed format)::

       {"duration_minutes": {"min": 10, "max": 20}, "participants": 1}

   Values may be a rule dict or a fixed literal (treated as required with
   an exact value match).

2. Structured definition list (ADR-041)::

       [
         {"key": "count", "title": "Count", "type": "integer",
          "required": true, "min": 1, "max": 100, "unit_group": "strikes"},
         {"key": "intensity", "title": "Intensity", "type": "enum",
          "options": ["1", "2", "3", "4", "5"], "allow_custom_value": false},
         {"key": "position", "title": "Position", "type": "string",
          "visible_when": {"count": {"min": 1}}}
       ]

Supported types: string, text, integer, decimal, boolean, enum,
multi_enum, duration. Validation is purely declarative — no eval.
"""

from __future__ import annotations

from typing import Any

# ── Parameter types (ADR-041) ──────────────────────────────────────────

PARAM_TYPES: tuple[str, ...] = (
    "string",
    "text",
    "integer",
    "decimal",
    "boolean",
    "enum",
    "multi_enum",
    "duration",
    # update2.md §8: reference selectors
    "inventory_selector",
    "body_part_selector",
    "location_selector",
)

# Legacy type names → canonical
_TYPE_ALIASES: dict[str, str] = {
    "number": "decimal",
    "str": "string",
    "int": "integer",
    "float": "decimal",
    "bool": "boolean",
}

# Common reusable parameter definitions (from examples/update.md)
COMMON_PARAMETERS: dict[str, dict[str, Any]] = {
    "tool": {"title": "Tool", "type": "string", "required": False},
    "target_area": {"title": "Target area", "type": "string", "required": False},
    "count": {"title": "Count", "type": "integer", "required": False, "min": 1},
    "unit": {"title": "Unit", "type": "string", "required": False},
    "duration": {"title": "Duration", "type": "duration", "required": False},
    "intensity": {
        "title": "Intensity",
        "type": "enum",
        "options": ["1", "2", "3", "4", "5"],
        "required": False,
        "allow_custom_value": False,
    },
    "position": {"title": "Position", "type": "string", "required": False},
    "role": {"title": "Role", "type": "string", "required": False},
    "modifiers": {"title": "Modifiers", "type": "multi_enum", "options": [], "required": False},
    "clothing": {"title": "Clothing", "type": "string", "required": False},
    "restraint": {"title": "Restraint", "type": "string", "required": False},
    "timing": {"title": "Timing", "type": "string", "required": False},
    "notes": {"title": "Notes", "type": "text", "required": False},
}


def canonical_type(t: str | None) -> str | None:
    """Map legacy/aliased type names onto the canonical ADR-041 set."""
    if t is None:
        return None
    return _TYPE_ALIASES.get(t, t)


# ── Schema normalization ────────────────────────────────────────────────


def normalize_schema(schema: Any) -> list[dict[str, Any]]:
    """Normalize any accepted schema shape into a list of param definitions.

    Returns [] for None/empty. Raises ValueError on structurally invalid input.
    """
    if not schema:
        return []
    if isinstance(schema, list):
        # Structured definition list (ADR-041)
        return [_normalize_definition(d) for d in schema]
    if isinstance(schema, dict):
        # Legacy compact map OR a single structured definition
        if "key" in schema and "type" in schema:
            return [_normalize_definition(schema)]
        defs: list[dict[str, Any]] = []
        for key, rules in schema.items():
            if isinstance(rules, dict):
                d = dict(rules)
                d.setdefault("key", key)
                # Legacy contract (LLM validator): keys are REQUIRED by default
                # unless explicitly marked optional (backward compat).
                if "optional" in d:
                    d["required"] = not d.pop("optional")
                else:
                    d.setdefault("required", True)
                defs.append(_normalize_definition(d))
            else:
                # Fixed literal value → required exact-match rule
                defs.append(
                    {
                        "key": str(key),
                        "title": str(key),
                        "type": "literal",
                        "required": True,
                        "value": rules,
                    }
                )
        return defs
    raise ValueError(f"params_schema must be a dict or list, got {type(schema).__name__}")


def _normalize_definition(d: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(d, dict):
        raise ValueError("param definition must be an object")
    key = d.get("key")
    if not key:
        raise ValueError("param definition missing 'key'")
    t = canonical_type(d.get("type"))
    if t is None:
        # Infer type from rule hints (legacy compact format):
        # min/max → numeric, enum/options → enum, min_length → string.
        if any(b in d for b in ("min", "max")):
            t = "decimal"
        elif "enum" in d or "options" in d:
            t = "enum"
        elif any(k in d for k in ("min_length", "max_length")):
            t = "string"
        else:
            t = "string"
    if t not in PARAM_TYPES:
        raise ValueError(f"unknown param type '{t}' for '{key}' (allowed: {', '.join(PARAM_TYPES)})")
    out = dict(d)
    out["key"] = str(key)
    out["type"] = t
    out.setdefault("title", str(key))
    out.setdefault("required", False)
    if t == "enum":
        # Legacy schemas use the ``enum`` key; structured ones use ``options``.
        if out.get("options") is None and out.get("enum"):
            out["options"] = out["enum"]
        if not out.get("options"):
            raise ValueError(f"enum param '{key}' requires 'options'")
    if t == "multi_enum" and not isinstance(out.get("options"), list):
        out["options"] = []
    # Reference selectors (update2.md §8) — validate shape
    if t in ("inventory_selector", "body_part_selector", "location_selector"):
        out.setdefault("selection_mode", "single")
        if t == "inventory_selector":
            out.setdefault("allowed_categories", [])
            out.setdefault("allowed_usage_roles", [])
            out.setdefault("allow_custom_value", False)
        if t == "body_part_selector":
            out.setdefault("allowed_body_systems", [])
            out.setdefault("allow_side_selection", True)
        if t == "location_selector":
            out.setdefault("allowed_location_types", [])
            out.setdefault("include_user_custom_locations", True)
    return out


# ── Validation (no eval) ────────────────────────────────────────────────


def validate_params(schema: Any, params: Any) -> list[str]:
    """Validate a params payload against a schema. Returns error list (empty = OK)."""
    if not schema:
        return []
    try:
        defs = normalize_schema(schema)
    except ValueError as e:
        # Config mistake (e.g. unknown type) surfaces as a validation error
        # rather than crashing the caller (backward-compatible contract).
        return [f"UNKNOWN_PARAM_TYPE: {e}"]
    if params is None:
        return ["PARAMS_NOT_DICT"] if any(d.get("required") for d in defs) else []
    if not isinstance(params, dict):
        return ["PARAMS_NOT_DICT"]

    errors: list[str] = []
    for d in defs:
        key = d["key"]
        present = key in params
        if not present:
            if d.get("required"):
                errors.append(f"MISSING_PARAM: {key}")
            continue
        errors.extend(_validate_value(key, params[key], d))
    return errors


def _validate_value(key: str, value: Any, d: dict[str, Any]) -> list[str]:
    t = d["type"]
    if t == "literal":
        if value != d.get("value"):
            return [f"PARAM_VALUE_MISMATCH: {key} expected {d.get('value')!r} got {value!r}"]
        return []

    # enum
    if t == "enum":
        options = d.get("options", [])
        if value in options:
            return []
        if d.get("allow_custom_value"):
            return []  # custom strings allowed
        return [f"PARAM_NOT_IN_ENUM: {key}={value!r} not in {options}"]

    if t == "multi_enum":
        if not isinstance(value, list):
            return [f"PARAM_TYPE_MISMATCH: {key} expected list got {type(value).__name__}"]
        options = d.get("options", [])
        if options:
            unknown = [v for v in value if v not in options]
            if unknown and not d.get("allow_custom_value"):
                return [f"PARAM_NOT_IN_ENUM: {key}={unknown!r} not in {options}"]
        return []

    # boolean
    if t == "boolean":
        if isinstance(value, bool):
            return []
        return [f"PARAM_TYPE_MISMATCH: {key} expected boolean got {type(value).__name__}"]

    # numeric
    if t in ("integer", "decimal", "duration"):
        if isinstance(value, bool):
            return [f"PARAM_TYPE_MISMATCH: {key} expected {t} got boolean"]
        if t == "integer" and not isinstance(value, int):
            return [f"PARAM_TYPE_MISMATCH: {key} expected integer got {type(value).__name__}"]
        if t in ("decimal", "duration") and not isinstance(value, int | float):
            return [f"PARAM_TYPE_MISMATCH: {key} expected {t} got {type(value).__name__}"]
        errors: list[str] = []
        if "min" in d and value < d["min"]:
            errors.append(f"PARAM_BELOW_MIN: {key}={value} < {d['min']}")
        if "max" in d and value > d["max"]:
            errors.append(f"PARAM_ABOVE_MAX: {key}={value} > {d['max']}")
        return errors

    # string / text
    if t in ("string", "text"):
        if not isinstance(value, str):
            return [f"PARAM_TYPE_MISMATCH: {key} expected {t} got {type(value).__name__}"]
        errors = []
        if "min_length" in d and len(value) < d["min_length"]:
            errors.append(f"PARAM_TOO_SHORT: {key} length={len(value)} < {d['min_length']}")
        if "max_length" in d and len(value) > d["max_length"]:
            errors.append(f"PARAM_TOO_LONG: {key} length={len(value)} > {d['max_length']}")
        if "enum" in d and value not in d["enum"]:
            errors.append(f"PARAM_NOT_IN_ENUM: {key}={value!r} not in {d['enum']}")
        return errors

    # reference selectors (update2.md §8) — validate shape only;
    # existence of referenced IDs is checked at service/API layer
    if t in ("inventory_selector", "body_part_selector", "location_selector"):
        mode = d.get("selection_mode", "single")
        if mode == "single":
            if not isinstance(value, str):
                return [f"PARAM_TYPE_MISMATCH: {key} expected a single ID string"]
            return []
        if mode == "multiple":
            if not isinstance(value, list):
                return [f"PARAM_TYPE_MISMATCH: {key} expected a list of IDs"]
            for i, v in enumerate(value):
                if not isinstance(v, str):
                    return [f"PARAM_TYPE_MISMATCH: {key}[{i}] expected string ID"]
            return []
        return []

    return []
