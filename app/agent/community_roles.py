"""Community Roles & Multi-Top Co-Governance Engine."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.community_roles import CommunityMemberRole

logger = logging.getLogger(__name__)

VALID_ROLE_TYPES = {
    "co_top",
    "keyholder",
    "trainer",
    "care_curator",
    "tournament_organizer",
}


async def assign_community_role(
    db: AsyncSession,
    community_id: uuid.UUID,
    user_id: uuid.UUID,
    role_type: str,
) -> dict[str, Any]:
    """Grants a granular co-governance role to a user in a community."""
    if role_type not in VALID_ROLE_TYPES:
        return {"status": "error", "reason": "invalid_role_type"}

    existing = (
        await db.execute(
            select(CommunityMemberRole).where(
                CommunityMemberRole.community_id == community_id,
                CommunityMemberRole.user_id == user_id,
                CommunityMemberRole.role_type == role_type,
            )
        )
    ).scalar_one_or_none()

    if existing:
        return {"status": "already_exists", "role_type": role_type}

    new_role = CommunityMemberRole(
        community_id=community_id,
        user_id=user_id,
        role_type=role_type,
    )
    db.add(new_role)
    await db.flush()

    return {"status": "success", "community_id": str(community_id), "user_id": str(user_id), "role_type": role_type}


async def get_community_user_roles(
    db: AsyncSession,
    community_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[str]:
    """Gets assigned role types for a user in a community."""
    roles_res = await db.execute(
        select(CommunityMemberRole.role_type).where(
            CommunityMemberRole.community_id == community_id,
            CommunityMemberRole.user_id == user_id,
        )
    )
    return list(roles_res.scalars().all())
