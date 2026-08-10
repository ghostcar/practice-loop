"""LLM response validator: verify entity_id belongs to user, params match schema.

Implements REMEDIATION_SPEC.md §7.4: LLM cannot expand the catalog or escape
underlying safety gates. Validator must reject malformed params (out-of-range,
wrong type, unknown enum values) so callers surface a clear error instead of
silently accepting a structurally invalid payload.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def validate_llm_response(parsed: dict, allowed_ids: set[str]) -> list[str]:
    """Validate LLM response against allowed set. Returns list of error codes (empty = valid).

    Top-level structural checks (always run):
    - entity_id is present and belongs to the user's allowed set
    - entity_name is present
    - params is a dict (if present)

    Schema-driven checks (only when a params_schema is supplied — see
    validate_params_against_schema) are performed separately by the caller,
    which has access to the entity row and its params_schema.
    """
    errors = []

    entity_id = parsed.get("entity_id")
    if not entity_id:
        errors.append("MISSING_ENTITY_ID")
    elif str(entity_id) not in allowed_ids:
        errors.append(f"FORBIDDEN_ENTITY_ID: {entity_id}")

    entity_name = parsed.get("entity_name")
    if not entity_name:
        errors.append("MISSING_ENTITY_NAME")

    params = parsed.get("params")
    if params is not None and not isinstance(params, dict):
        errors.append("INVALID_PARAMS_TYPE")

    return errors


def get_allowed_ids(context: dict) -> set[str]:
    """Extract set of allowed entity IDs from context."""
    return {e["id"] for e in context.get("allowed_entities", [])}


# ---------------------------------------------------------------------------
# Params-schema validation (REM §7.4) — REM extract of behavioral safety.

# Supported JSON-schema-lite constructs for params_schema. We deliberately
# keep the surface tiny to avoid pulling in a full JSON-schema library:
#
# {
#   "duration_minutes": {
#     "type": "number", "min": 5, "max": 240,
#     "description": "How long the activity lasts in minutes"
#   },
#   "intensity": {
#     "type": "string", "enum": ["low", "medium", "high"]
#   },
#   "category": {"type": "string", "max_length": 100},
#   "notes": {"type": "string", "max_length": 1000, "optional": true}
# }
#
# Each property accepts:
#   - type: "number" | "integer" | "string" | "boolean"
#   - min / max (for numeric types)
#   - min_length / max_length (for string)
#   - enum (for string) — list of allowed values
#   - optional (default false) — if true, missing key is NOT a validation error

_TYPE_VALIDATORS: dict[str, type] = {
    "number": (int, float),
    "integer": int,
    "string": str,
    "boolean": bool,
}


def validate_params_against_schema(params: Any, schema: dict | None) -> list[str]:
    """Validate a `params` payload against an entity's params_schema.

    Returns a list of error codes (empty list = valid). Never raises — the
    caller decides whether errors block or just warn.

    Behaviour:
    - If schema is None/empty → no per-key checks performed.
    - Each declared key MUST be present unless `optional=True`.
    - Each value MUST match `type` (numeric, integer, string, boolean).
    - Numeric types bounded by inclusive `min` / `max`.
    - Strings bounded by inclusive `min_length` / `max_length`.
    - Strings restricted to `enum` if provided.
    - Extra keys (not declared in schema) are NOT rejected — schemas are
      intentionally non-exhaustive so admins can add freedom in future
      without breaking older validator versions.
    """
    if not schema:
        return []
    if not isinstance(params, dict):
        return ["PARAMS_NOT_DICT"]

    errors: list[str] = []
    for key, rules in schema.items():
        if key not in params:
            if rules.get("optional"):
                continue
            errors.append(f"MISSING_PARAM: {key}")
            continue
        value = params[key]
        errors.extend(_validate_one_param(key, value, rules))
    return errors


def _validate_one_param(key: str, value: Any, rules: dict) -> list[str]:
    """Validate a single param value against its sub-schema."""
    declared_type = rules.get("type")
    if not declared_type:
        # No type → accept as-is (treat as "any"); still check envelope rules.
        return []

    allowed_types = _TYPE_VALIDATORS.get(declared_type)
    if allowed_types is None:
        return [f"UNKNOWN_PARAM_TYPE: {declared_type} for {key}"]

    if not isinstance(value, allowed_types):
        return [f"PARAM_TYPE_MISMATCH: {key} expected {declared_type} got {type(value).__name__}"]

    # bool is subclass of int — guard against accidental int-as-bool:
    if declared_type == "integer" and isinstance(value, bool):
        return [f"PARAM_TYPE_MISMATCH: {key} expected integer got boolean"]

    errors: list[str] = []

    # Numeric bounds.
    if declared_type in ("number", "integer"):
        if "min" in rules and value < rules["min"]:
            errors.append(f"PARAM_BELOW_MIN: {key}={value} < {rules['min']}")
        if "max" in rules and value > rules["max"]:
            errors.append(f"PARAM_ABOVE_MAX: {key}={value} > {rules['max']}")

    # String envelope.
    if declared_type == "string":
        if "min_length" in rules and len(value) < rules["min_length"]:
            errors.append(f"PARAM_TOO_SHORT: {key} length={len(value)} < {rules['min_length']}")
        if "max_length" in rules and len(value) > rules["max_length"]:
            errors.append(f"PARAM_TOO_LONG: {key} length={len(value)} > {rules['max_length']}")

        enum_values = rules.get("enum")
        if enum_values and value not in enum_values:
            errors.append(f"PARAM_NOT_IN_ENUM: {key}={value!r} not in {enum_values}")

    return errors
