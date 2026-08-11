"""LLM response validator: verify entity_id belongs to user, params match schema.

Implements REMEDIATION_SPEC.md §7.4: LLM cannot expand the catalog or escape
underlying safety gates. Validator must reject malformed params (out-of-range,
wrong type, unknown enum values) so callers surface a clear error instead of
silently accepting a structurally invalid payload.
"""

import logging
from typing import Any

from app.params import validate_params

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
# Params-schema validation (REM §7.4) — delegated to the typed DSL (ADR-041).
# The DSL accepts both the legacy compact map format (rules without "type"
# are inferred, keys required by default unless optional) and the structured
# definition list (key/title/type/required/options/min/max/visible_when/
# allow_custom_value).


def validate_params_against_schema(params: Any, schema: dict | None) -> list[str]:
    """Validate a `params` payload against an entity's params_schema.

    Returns a list of error codes (empty list = valid). Never raises — the
    caller decides whether errors block or just warn.

    Delegates to the typed parameter DSL (app/params.py, ADR-041), which
    accepts both the legacy compact map format and the structured
    definition list (key/title/type/required/options/min/max/visible_when/
    allow_custom_value). Extra keys are not rejected — schemas are
    intentionally non-exhaustive.
    """
    if not schema:
        return []
    return validate_params(schema, params)
