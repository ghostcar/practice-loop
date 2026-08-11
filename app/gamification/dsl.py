"""Typed gamification condition DSL (REM §5.2 / audit P2).

Gamification conditions are stored as plain strings (e.g. ``extra_fluid_ml > 0``).
They are NEVER executed via ``eval`` — instead this module:

- validates the syntax against a small whitelist of operators and value shapes
  (``field op value`` or a bare truthy field name);
- provides a tiny evaluator used by the points engine.

Field names are restricted to ``[A-Za-z_][A-Za-z0-9_]*`` and values to numbers,
``true``/``false``, or short quoted strings — so a stored condition cannot smuggle
arbitrary code into the runtime.
"""

from __future__ import annotations

import re
from typing import Any

# Operators supported by the evaluator (whitelist — no eval, no arbitrary code).
_OPS = (">", "<", ">=", "<=", "==", "!=")

_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
_QUOTED_RE = re.compile(r"^'[^']{0,100}'$|^\"[^\"]{0,100}\"$")

# Failure conditions for penalty levels (whitelist).
PENALTY_CONDITIONS = ("missed", "partial", "late")


def validate_condition(condition: str | None) -> str | None:
    """Validate a bonus condition string. Returns an error message or None.

    Accepts either:
      - a bare field name:  ``extra_fluid_ml``  (truthy check)
      - ``field op value``: ``extra_fluid_ml > 0``, ``level_jump == true``

    The value may be a number, ``true``/``false``, or a short quoted string.
    """
    if not condition:
        return None
    condition = condition.strip()
    if not condition:
        return None

    if " " not in condition:
        if not _FIELD_RE.match(condition):
            return f"invalid field name: {condition!r}"
        return None

    parts = condition.split()
    if len(parts) != 3:
        return f"condition must be 'field op value' or a bare field: {condition!r}"
    key, op, val = parts

    if not _FIELD_RE.match(key):
        return f"invalid field name: {key!r}"
    if op not in _OPS:
        return f"unsupported operator {op!r} (allowed: {', '.join(_OPS)})"
    if not (_NUMBER_RE.match(val) or val.lower() in ("true", "false") or _QUOTED_RE.match(val)):
        return f"invalid value: {val!r}"

    return None


def validate_penalty_condition(condition: str | None) -> str | None:
    """Validate a penalty-level failure condition (whitelist)."""
    if condition is None:
        return None
    if condition not in PENALTY_CONDITIONS:
        return f"unknown failure condition {condition!r} (allowed: {', '.join(PENALTY_CONDITIONS)})"
    return None


def eval_condition(condition: str, params: dict) -> bool:
    """Evaluate a typed condition against a params dict (never eval)."""
    if not condition:
        return False
    condition = condition.strip()

    # Bare field name — truthy check.
    if " " not in condition:
        return bool(params.get(condition, False))

    parts = condition.split()
    if len(parts) != 3:
        return False
    key, op, val = parts

    actual = params.get(key)
    if actual is None:
        return False

    # Numeric comparison first.
    try:
        actual_num = float(actual)
        val_num = float(val)
        if op == ">":
            return actual_num > val_num
        if op == "<":
            return actual_num < val_num
        if op == ">=":
            return actual_num >= val_num
        if op == "<=":
            return actual_num <= val_num
        if op == "==":
            return actual_num == val_num
        if op == "!=":
            return actual_num != val_num
    except (ValueError, TypeError):
        pass

    # String / boolean comparison (strip quotes from the literal).
    actual_str = str(actual).lower()
    val_str = val.strip("\"'").lower()
    if op == "==":
        return actual_str == val_str
    if op == "!=":
        return actual_str != val_str
    return False


def find_param_key(condition: str, params: dict) -> str | None:
    """Extract the field name referenced by a condition (if present in params)."""
    if not condition:
        return None
    key = condition.split()[0] if " " in condition else condition
    return key if key in params else None


def _coerce_number(value: Any) -> float | None:
    """Best-effort numeric coercion used by callers."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
