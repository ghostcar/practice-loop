"""Capability Authorizer & Adapters (Ports & Adapters / Revision 2).

Unified actor-to-actor authorization service.
Evaluates:
1. Direct CapabilityGrantV2 grants
2. Legacy D/s Suite CapabilityGrant adapter
3. Legacy SocialGrant adapter
4. Community Member Delegation adapter
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capability import CapabilityGrantV2

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ActorContext:
    """Unified actor calling context for audit and authorization."""

    actor_id: uuid.UUID
    actor_type: str = "human"  # human | agent | system
    source: str = "web"  # web | mobile | telegram | scheduler | ai_automated


class CapabilityAuthorizer:
    """Ports & Adapters Authorizer for cross-actor operations."""

    @staticmethod
    async def can_act(
        db: AsyncSession,
        actor: ActorContext,
        issuer_user_id: uuid.UUID,
        capability_code: str,
        resource_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Check if actor is authorized to perform action on issuer's behalf.

        Returns (is_allowed, reason).
        """
        # 1. Owner always has full capability over own domain
        if actor.actor_id == issuer_user_id:
            return True, "Owner has full authorization."

        now = datetime.datetime.now(datetime.UTC)

        # 2. Check Direct CapabilityGrantV2
        v2_query = select(CapabilityGrantV2).where(
            CapabilityGrantV2.issuer_id == issuer_user_id,
            CapabilityGrantV2.recipient_id == actor.actor_id,
            CapabilityGrantV2.capability_code == capability_code,
            CapabilityGrantV2.status == "active",
            CapabilityGrantV2.valid_from <= now,
            (CapabilityGrantV2.valid_until.is_(None) | (CapabilityGrantV2.valid_until >= now)),
        )
        v2_res = await db.execute(v2_query)
        grant_v2 = v2_res.scalar_one_or_none()

        if grant_v2 is not None:
            # Check resource scope
            if resource_id and grant_v2.resource_scope:
                res_str = str(resource_id)
                allowed_ids = grant_v2.resource_scope.get("allowed_ids", [])
                if allowed_ids and res_str not in allowed_ids:
                    return False, f"Resource {res_str} not permitted by grant scope."

            return True, f"Authorized by direct CapabilityGrantV2 ({grant_v2.id})."

        # 3. Adapter: Legacy D/s CapabilityGrant
        ds_allowed, ds_reason = await _check_legacy_ds_grant(db, actor.actor_id, issuer_user_id, capability_code)
        if ds_allowed:
            return True, ds_reason

        # 4. Adapter: Legacy SocialGrant
        soc_allowed, soc_reason = await _check_legacy_social_grant(db, actor.actor_id, issuer_user_id, capability_code)
        if soc_allowed:
            return True, soc_reason

        # 5. Adapter: Community Member Delegation
        comm_allowed, comm_reason = await _check_community_delegation(
            db, actor.actor_id, issuer_user_id, capability_code
        )
        if comm_allowed:
            return True, comm_reason

        return False, f"Capability '{capability_code}' denied: no active grant found for actor {actor.actor_id}."


# ─────────────────────────────────────────────────────────────────────────────
# Adapters for Legacy Grant Models (Ports & Adapters boundary isolation)
# ─────────────────────────────────────────────────────────────────────────────


async def _check_legacy_ds_grant(
    db: AsyncSession,
    actor_id: uuid.UUID,
    issuer_id: uuid.UUID,
    capability_code: str,
) -> tuple[bool, str]:
    """Adapter translating legacy D/s CapabilityGrant boolean scopes into capability codes."""
    try:
        from app.models.ds_suite import CapabilityGrant

        query = select(CapabilityGrant).where(
            CapabilityGrant.sub_user_id == issuer_id,
            CapabilityGrant.top_user_id == actor_id,
            CapabilityGrant.status == "active",
        )
        res = await db.execute(query)
        grant = res.scalar_one_or_none()
        if grant is None:
            return False, "No active D/s grant"

        # Map capability domains to D/s scopes
        domain = capability_code.split(".")[0]
        scope_map = {
            "training": grant.scope_training,
            "diet": grant.scope_tasks,
            "care": grant.scope_aftercare,
            "aftercare": grant.scope_aftercare,
            "medication": grant.scope_medication,
            "health": grant.scope_health_view,
            "state": grant.scope_health_view,
            "tasks": grant.scope_tasks,
            "activity": grant.scope_tasks,
            "timer": grant.scope_chastity,
            "chastity": grant.scope_chastity,
            "inventory": grant.scope_inventory,
            "protocol": grant.scope_tasks or grant.scope_aftercare,
        }

        if scope_map.get(domain, False):
            return True, f"Authorized by legacy D/s CapabilityGrant ({grant.id}) for domain '{domain}'."

    except Exception as exc:
        logger.debug("D/s adapter error: %s", exc)

    return False, "D/s grant scope not granted"


async def _check_legacy_social_grant(
    db: AsyncSession,
    actor_id: uuid.UUID,
    issuer_id: uuid.UUID,
    capability_code: str,
) -> tuple[bool, str]:
    """Adapter translating SocialGrant into capability codes."""
    try:
        from app.models.social import SocialGrant

        domain = capability_code.split(".")[0]
        query = select(SocialGrant).where(
            SocialGrant.relationship_id.is_not(None),
            SocialGrant.subject_type == domain,
            SocialGrant.status == "active",
        )
        res = await db.execute(query)
        grants = res.scalars().all()
        if grants:
            return True, f"Authorized by legacy SocialGrant for subject '{domain}'."
    except Exception as exc:
        logger.debug("Social adapter error: %s", exc)

    return False, "Social grant not granted"


async def _check_community_delegation(
    db: AsyncSession,
    actor_id: uuid.UUID,
    issuer_id: uuid.UUID,
    capability_code: str,
) -> tuple[bool, str]:
    """Adapter translating CommunityMemberDelegation into capability codes."""
    try:
        from app.models.community_agent import CommunityMemberDelegation

        query = select(CommunityMemberDelegation).where(
            CommunityMemberDelegation.user_id == issuer_id,
            CommunityMemberDelegation.delegate_user_id == actor_id,
            CommunityMemberDelegation.status == "active",
        )
        res = await db.execute(query)
        del_entry = res.scalar_one_or_none()
        if del_entry is not None:
            return True, f"Authorized by CommunityMemberDelegation ({del_entry.scope})."
    except Exception as exc:
        logger.debug("Community adapter error: %s", exc)

    return False, "Community delegation not granted"
