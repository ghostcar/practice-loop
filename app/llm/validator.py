"""LLM response validator: verify entity_id belongs to user, params match schema."""

import logging

logger = logging.getLogger(__name__)


def validate_llm_response(parsed: dict, allowed_ids: set[str]) -> list[str]:
    """Validate LLM response against allowed set. Returns list of error codes (empty = valid).

    Checks:
    - entity_id is present and belongs to the user's allowed set
    - entity_name is present
    - params is a dict (if present)
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
