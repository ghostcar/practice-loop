"""Points v2 engine: flexible calculation from Entity.gamification_config JSON.

Reads gamification_config from Entity (or falls back to XP system).
Supports: base points, per-entity penalty levels, bonus conditions, thresholds.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.points import PointsTransaction

logger = logging.getLogger(__name__)


async def calculate_entity_points(
    entity_config: dict | None,
    params: dict | None = None,
) -> tuple[int, list[str], list[str]]:
    """Calculate points, bonuses, and penalties for completing a task.

    Args:
        entity_config: The Entity.gamification_config JSON dict.
        params: Selected params from ActivityLog (may contain intensity, extra_fluid_ml, etc.)

    Returns:
        (net_points, bonus_descriptions, penalty_descriptions)
    """
    if not entity_config or not isinstance(entity_config, dict):
        return 0, [], []

    params = params or {}

    # 1. Base points
    points_cfg = entity_config.get("points", {})
    base = points_cfg.get("base", 10)

    # Intensity multiplier from params
    intensity = params.get("intensity", 1)
    base = int(base * (1 + (intensity - 1) * 0.10))

    # 2. Bonuses
    bonuses = entity_config.get("bonuses", [])
    bonus_descriptions: list[str] = []
    bonus_total = 0
    for b in bonuses:
        if not b.get("enabled", True):
            continue
        if _eval_condition(b.get("condition", ""), params):
            reward = b.get("reward", 0)
            if b.get("per_unit"):
                # Find the matching param key
                key = _find_param_key(b.get("condition", ""), params)
                count = params.get(key, 0) if key else 0
                reward = reward * max(0, count)
            bonus_total += reward
            bonus_descriptions.append(f"+{reward} {b.get('description', b.get('code', 'bonus'))}")

    # 3. Penalties (only applied on interruption, not here)
    penalty_descriptions: list[str] = []

    return base + bonus_total, bonus_descriptions, penalty_descriptions


async def calculate_entity_penalty(
    entity_config: dict | None,
    failure_condition: str = "missed",
    escalation_level: int = 1,
) -> int:
    """Calculate points deduction for a failed task.

    Args:
        entity_config: The Entity.gamification_config JSON dict.
        failure_condition: What happened (missed / partial / late).
        escalation_level: How many consecutive failures.

    Returns:
        Negative points to deduct.
    """
    if not entity_config or not isinstance(entity_config, dict):
        return 25  # Default penalty

    penalties_cfg = entity_config.get("penalties", {})
    if not penalties_cfg.get("enabled", True):
        return 0

    levels = penalties_cfg.get("levels", [])
    if not levels:
        return 25

    # Find matching level
    for level_cfg in levels:
        if level_cfg.get("condition") == failure_condition:
            deduction = level_cfg.get("deduction", 0)
            # Apply escalation
            if penalties_cfg.get("escalation"):
                step = penalties_cfg.get("escalation_step", 1.5)
                cap = penalties_cfg.get("escalation_cap", 5)
                mult = min(1.0 + (escalation_level - 1) * (step - 1.0), float(cap))
                deduction = int(deduction * mult)
            return deduction

    return 25  # Fallback


async def get_redemption_action(
    entity_config: dict | None,
    failure_condition: str = "missed",
) -> dict | None:
    """Get the redemption action for a penalty (e.g., clothespins duration)."""
    if not entity_config or not isinstance(entity_config, dict):
        return None

    penalties_cfg = entity_config.get("penalties", {})
    if not penalties_cfg.get("enabled", True):
        return None

    for level_cfg in penalties_cfg.get("levels", []):
        if level_cfg.get("condition") == failure_condition and level_cfg.get("redemption"):
            return level_cfg["redemption"]

    return None


async def award_points(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    transaction_type: str,
    reason: str = "",
    entity_id: uuid.UUID | None = None,
    activity_log_id: uuid.UUID | None = None,
    meta: dict | None = None,
) -> PointsTransaction:
    """Record a points transaction."""
    txn = PointsTransaction(
        user_id=user_id,
        amount=amount,
        transaction_type=transaction_type,
        reason=reason,
        entity_id=entity_id,
        activity_log_id=activity_log_id,
        meta=meta,
    )
    db.add(txn)
    await db.flush()
    return txn


# ── Condition evaluator ──


def _eval_condition(condition: str, params: dict) -> bool:
    """Simple condition evaluator for bonus conditions.

    Supports: 'key > value', 'key == value', 'key != value', 'key', 'key < value'
    Example: 'extra_fluid_ml > 0', 'level_jump == true'
    """
    if not condition:
        return False

    condition = condition.strip()

    # Just a key name — check if truthy
    if " " not in condition:
        return bool(params.get(condition, False))

    # Comparison
    parts = condition.split()
    if len(parts) != 3:
        return False

    key, op, val = parts
    actual = params.get(key)

    if actual is None:
        return False

    # Try numeric comparison
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

    # String comparison
    actual_str = str(actual).lower()
    val_str = val.lower()
    if op == "==":
        return actual_str == val_str
    if op == "!=":
        return actual_str != val_str

    return False


def _find_param_key(condition: str, params: dict) -> str | None:
    """Extract the param key from a condition string."""
    if not condition:
        return None
    key = condition.split()[0] if " " in condition else condition
    return key if key in params else None
