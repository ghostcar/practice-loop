"""Unified AI Proposal Pipeline (Ports & Adapters / Revision 2 / ADR-106).

Routes AI persona suggestions, automated triggers, and scheduled tasks
through standardized application services with Agency Policy evaluation.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agency import AgencyLevel
from app.services.agency import evaluate_agency_permission
from app.services.capability import ActorContext

logger = logging.getLogger(__name__)


class ProposalResult:
    def __init__(
        self,
        approved: bool,
        status: str,  # "applied" | "proposed_pending_confirmation" | "rejected"
        action_type: str,
        payload: dict[str, Any],
        rejection_reason: str | None = None,
    ) -> None:
        self.approved = approved
        self.status = status
        self.action_type = action_type
        self.payload = payload
        self.rejection_reason = rejection_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "status": self.status,
            "action_type": self.action_type,
            "payload": self.payload,
            "rejection_reason": self.rejection_reason,
        }


async def submit_ai_proposal(
    db: AsyncSession,
    user_id: uuid.UUID,
    domain: str,
    operation: str,
    action_payload: dict[str, Any],
    persona_id: uuid.UUID | None = None,
) -> ProposalResult:
    """Submit an AI proposal through Agency Policy gates and bounds."""
    from app.services.agency import get_user_agency_policy

    policy = await get_user_agency_policy(db, user_id, domain)
    effective_level = (
        policy.operation_overrides.get(operation, policy.default_level) if policy else AgencyLevel.MANUAL.value
    )

    allowed, reason = await evaluate_agency_permission(
        db=db,
        user_id=user_id,
        domain=domain,
        operation=operation,
        proposed_level=effective_level,
        payload=action_payload,
    )

    if not allowed:
        return ProposalResult(
            approved=False,
            status="rejected",
            action_type=operation,
            payload=action_payload,
            rejection_reason=reason,
        )

    actor = ActorContext(
        actor_id=user_id,
        actor_type="ai_proposal",
        source=f"persona_{persona_id}" if persona_id else "ai_pipeline",
    )

    # 2. Route by agency level
    if effective_level == AgencyLevel.AUTOMATED_WITHIN_POLICY.value:
        # Automatically executable action
        logger.info("[AIProposalPipeline] Auto-applying %s for user %s via %s", operation, user_id, actor)
        return ProposalResult(
            approved=True,
            status="applied",
            action_type=operation,
            payload=action_payload,
        )
    elif effective_level in (AgencyLevel.PROPOSE_AND_CONFIRM.value, AgencyLevel.ASSISTED.value):
        # Action requires user confirmation
        logger.info("[AIProposalPipeline] Proposed %s for user %s awaiting confirmation", operation, user_id)
        return ProposalResult(
            approved=True,
            status="proposed_pending_confirmation",
            action_type=operation,
            payload=action_payload,
        )
    else:
        # MANUAL / ANALYZE_ONLY: AI cannot propose or mutate
        return ProposalResult(
            approved=False,
            status="rejected",
            action_type=operation,
            payload=action_payload,
            rejection_reason="Domain is strictly in MANUAL or ANALYZE_ONLY mode.",
        )
