"""Tests for the extended LLM validator.

Covers REM §7.4: validator must reject malformed params (out-of-range, wrong
type, unknown enum values) so callers surface a clear error instead of silently
accepting a structurally invalid payload.
"""

import pytest

from app.llm.validator import (
    validate_llm_response,
    validate_params_against_schema,
)

# ---------------------------------------------------------------------------
# Top-level shape (unchanged)


def test_allow_unknown_key_passes_top_level():
    parsed = {"entity_id": "1", "entity_name": "n", "unrelated_key": "x"}
    assert validate_llm_response(parsed, {"1"}) == []


def test_missing_entity_id_failed():
    parsed = {"entity_name": "n"}
    errs = validate_llm_response(parsed, {"1"})
    assert "MISSING_ENTITY_ID" in errs


def test_forbidden_entity_id_failed():
    parsed = {"entity_id": "2", "entity_name": "n"}
    errs = validate_llm_response(parsed, {"1"})
    assert any(e.startswith("FORBIDDEN_ENTITY_ID") for e in errs)


def test_invalid_params_type_failed():
    parsed = {"entity_id": "1", "entity_name": "n", "params": "stringy"}
    errs = validate_llm_response(parsed, {"1"})
    assert "INVALID_PARAMS_TYPE" in errs


# ---------------------------------------------------------------------------
# Schema-driven validator

SCHEMA_NUM = {"duration_minutes": {"type": "number", "min": 5, "max": 240}}
SCHEMA_INT = {"count": {"type": "integer", "min": 1, "max": 10}}
SCHEMA_STRICT_STR = {"intensity": {"type": "string", "enum": ["low", "medium", "high"]}}
SCHEMA_BOUNDED_STR = {"title": {"type": "string", "min_length": 1, "max_length": 50}}
SCHEMA_OPTIONAL = {"notes": {"type": "string", "optional": True, "max_length": 200}}


@pytest.mark.parametrize(
    "params,schema",
    [
        (None, None),  # schema-less: always pass
        ({}, None),
        ({"a": 1}, None),
        ({}, {}),
        ({"duration_minutes": 30}, SCHEMA_NUM),
        ({"duration_minutes": 5}, SCHEMA_NUM),  # edge: min
        ({"duration_minutes": 240}, SCHEMA_NUM),  # edge: max
        ({"count": 5}, SCHEMA_INT),
        ({"intensity": "low"}, SCHEMA_STRICT_STR),
        ({"intensity": "high"}, SCHEMA_STRICT_STR),
        ({"title": "ok"}, SCHEMA_BOUNDED_STR),
        ({"notes": "anything"}, SCHEMA_OPTIONAL),  # optional present
        ({}, SCHEMA_OPTIONAL),  # optional missing
        ({"extra_unrelated_key": "free form"}, SCHEMA_OPTIONAL),  # non-exhaustive schema
    ],
)
def test_validate_params_passes_valid(params, schema):
    assert validate_params_against_schema(params, schema) == []


@pytest.mark.parametrize(
    "params,schema,expected_code",
    [
        ({"duration_minutes": 4}, SCHEMA_NUM, "PARAM_BELOW_MIN"),
        ({"duration_minutes": 241}, SCHEMA_NUM, "PARAM_ABOVE_MAX"),
        ({"duration_minutes": "30"}, SCHEMA_NUM, "PARAM_TYPE_MISMATCH"),
        ({"count": 0}, SCHEMA_INT, "PARAM_BELOW_MIN"),
        ({"count": 11}, SCHEMA_INT, "PARAM_ABOVE_MAX"),
        ({"count": 5.5}, SCHEMA_INT, "PARAM_TYPE_MISMATCH"),
        ({"intensity": "ultra"}, SCHEMA_STRICT_STR, "PARAM_NOT_IN_ENUM"),
        ({"title": ""}, SCHEMA_BOUNDED_STR, "PARAM_TOO_SHORT"),
        ({"title": "x" * 51}, SCHEMA_BOUNDED_STR, "PARAM_TOO_LONG"),
        ({}, SCHEMA_NUM, "MISSING_PARAM"),
    ],
)
def test_validate_params_returns_specific_codes(params, schema, expected_code):
    errs = validate_params_against_schema(params, schema)
    assert any(e.startswith(expected_code) for e in errs), errs


def test_validate_params_non_dict_payload():
    errs = validate_params_against_schema("not a dict", {"x": {"type": "string"}})
    assert any(e.startswith("PARAMS_NOT_DICT") for e in errs)


def test_validate_params_unknown_type_in_schema():
    """Admins can hit unknown types; validator must surface its config mistake."""
    errs = validate_params_against_schema({"x": 1}, {"x": {"type": "datetime"}})
    assert any(e.startswith("UNKNOWN_PARAM_TYPE") for e in errs)


def test_validate_params_bool_is_not_integer():
    errs = validate_params_against_schema({"count": True}, {"count": {"type": "integer"}})
    assert any(e.startswith("PARAM_TYPE_MISMATCH") for e in errs)


def test_validate_params_accepts_int_under_number():
    """`type=number` allows int OR float — flexible for LLM-generated payloads."""
    errs = validate_params_against_schema({"x": 5}, {"x": {"type": "number", "min": 0, "max": 10}})
    assert errs == []
