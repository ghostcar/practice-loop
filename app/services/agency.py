"""Agency Service (Revision 2 / ADR-068 / ADR-106).

Evaluates user autonomy policies per domain and operation.
Implements the User Sovereignty principle:
- Platform defaults to MANUAL autonomy unless explicitly granted.
- User boundaries (constraints) are absolute HARD system gates.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agency import AgencyLevel, AgencyPolicy

logger = logging.getLogger(__name__)

# Standard operation hierarchy: lower is stricter, higher is more autonomous
AGENCY_LEVEL_WEIGHTS: dict[str, int] = {
    AgencyLevel.MANUAL.value: 0,
    AgencyLevel.ANALYZE_ONLY.value: 10,
    AgencyLevel.ASSISTED.value: 20,
    AgencyLevel.PROPOSE_AND_CONFIRM.value: 30,
    AgencyLevel.AUTOMATED_WITHIN_POLICY.value: 40,
    AgencyLevel.DELEGATED_AI.value: 50,
    AgencyLevel.DELEGATED_HUMAN.value: 60,
}


async def get_user_agency_policy(
    db: AsyncSession,
    user_id: uuid.UUID,
    domain: str,
) -> AgencyPolicy | None:
    """Retrieve the agency policy for a specific user and domain."""
    result = await db.execute(
        select(AgencyPolicy).where(
            AgencyPolicy.user_id == user_id,
            AgencyPolicy.domain == domain,
        )
    )
    return result.scalar_one_or_none()


async def set_user_agency_policy(
    db: AsyncSession,
    user_id: uuid.UUID,
    domain: str,
    default_level: str = AgencyLevel.MANUAL.value,
    operation_overrides: dict[str, str] | None = None,
    constraints: dict[str, Any] | None = None,
) -> AgencyPolicy:
    """Create or update the user's agency policy."""
    policy = await get_user_agency_policy(db, user_id, domain)
    if policy is None:
        policy = AgencyPolicy(
            user_id=user_id,
            domain=domain,
            default_level=default_level,
            operation_overrides=operation_overrides or {},
            constraints=constraints or {},
        )
        db.add(policy)
    else:
        policy.default_level = default_level
        if operation_overrides is not None:
            policy.operation_overrides = operation_overrides
        if constraints is not None:
            policy.constraints = constraints

    await db.flush()
    return policy


async def evaluate_agency_permission(
    db: AsyncSession,
    user_id: uuid.UUID,
    domain: str,
    operation: str,
    proposed_level: str = AgencyLevel.AUTOMATED_WITHIN_POLICY.value,
    payload: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Check if an action is permitted under the user's agency policy.

    Returns (is_allowed, reason).
    """
    policy = await get_user_agency_policy(db, user_id, domain)

    # 1. Resolve allowed level
    if policy is None:
        allowed_level_str = AgencyLevel.MANUAL.value
        user_constraints = {}
    else:
        allowed_level_str = policy.operation_overrides.get(operation, policy.default_level)
        user_constraints = policy.constraints or {}

    allowed_weight = AGENCY_LEVEL_WEIGHTS.get(allowed_level_str, 0)
    proposed_weight = AGENCY_LEVEL_WEIGHTS.get(proposed_level, 0)

    # If proposed level requires more autonomy than user allowed -> reject
    if proposed_weight > allowed_weight:
        return False, (
            f"Agency policy violation: operation '{domain}.{operation}' requires '{proposed_level}', "
            f"but user policy allows max '{allowed_level_str}'."
        )

    # 2. Check user-defined hard boundaries (Constraints)
    if payload and user_constraints:
        # Check max duration
        if (
            "max_duration_min" in user_constraints
            and "duration_min" in payload
            and payload["duration_min"] > user_constraints["max_duration_min"]
        ):
            return False, (
                f"User constraint violation: duration {payload['duration_min']}m exceeds "
                f"user limit {user_constraints['max_duration_min']}m."
            )

        # Check prohibited categories/tags
        if "forbidden_tags" in user_constraints and "tags" in payload:
            overlap = set(payload["tags"]).intersection(set(user_constraints["forbidden_tags"]))
            if overlap:
                return False, f"User constraint violation: contains forbidden tags {overlap}."

    return True, "Operation permitted by agency policy."
