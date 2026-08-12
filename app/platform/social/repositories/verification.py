"""Social verification — policies, requests, votes (S4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social.models import (
    SocialVerificationPolicy,
    SocialVerificationRequest,
    SocialVerificationVote,
)


async def create_verification_policy(
    db: AsyncSession,
    owner_id: uuid.UUID,
    name: str,
    verifier_scope: dict,
    *,
    min_approvals: int = 1,
    max_rejections: int | None = None,
    deadline_hours: int = 72,
    no_quorum_action: str = "review_required",
    require_reject_comment: bool = False,
) -> SocialVerificationPolicy:
    policy = SocialVerificationPolicy(
        owner_id=owner_id,
        name=name,
        verifier_scope=verifier_scope,
        min_approvals=min_approvals,
        max_rejections=max_rejections,
        deadline_hours=deadline_hours,
        no_quorum_action=no_quorum_action,
        require_reject_comment=require_reject_comment,
    )
    db.add(policy)
    await db.flush()
    return policy


async def create_verification_request(
    db: AsyncSession,
    policy_id: uuid.UUID,
    subject_id: uuid.UUID,
    requester_id: uuid.UUID,
    deadline_hours: int,
) -> SocialVerificationRequest:
    req = SocialVerificationRequest(
        policy_id=policy_id,
        subject_id=subject_id,
        requester_id=requester_id,
        deadline_at=datetime.utcnow() + __import__("datetime").timedelta(hours=deadline_hours),
    )
    db.add(req)
    await db.flush()
    return req


async def get_verification_request(
    db: AsyncSession,
    request_id: uuid.UUID,
) -> SocialVerificationRequest | None:
    result = await db.execute(select(SocialVerificationRequest).where(SocialVerificationRequest.id == request_id))
    return result.scalar_one_or_none()


async def cast_vote(
    db: AsyncSession,
    request_id: uuid.UUID,
    voter_id: uuid.UUID,
    value: str,
    comment: str | None = None,
) -> SocialVerificationVote | None:
    """Cast a vote. Returns None if already voted."""
    req = await get_verification_request(db, request_id)
    if req is None or req.state != "open":
        return None
    if req.requester_id == voter_id:
        return None  # owner cannot vote

    vote = SocialVerificationVote(
        request_id=request_id,
        voter_id=voter_id,
        value=value,
        comment=comment,
    )
    db.add(vote)
    await db.flush()

    # Update counters
    if value == "approve":
        req.approvals += 1
    elif value == "reject":
        req.rejections += 1
    await db.flush()

    return vote


async def check_quorum_and_finalize(
    db: AsyncSession,
    request_id: uuid.UUID,
) -> SocialVerificationRequest | None:
    """Check quorum after each vote. Finalizes if thresholds met."""
    req = await get_verification_request(db, request_id)
    if req is None or req.state != "open":
        return req

    policy_result = await db.execute(
        select(SocialVerificationPolicy).where(SocialVerificationPolicy.id == req.policy_id)
    )
    policy = policy_result.scalar_one_or_none()
    if policy is None:
        return req

    now = datetime.utcnow()

    # Check approvals
    if req.approvals >= policy.min_approvals:
        req.state = "verified"
        req.result_summary = f"Verified: {req.approvals} approvals"
        req.finalized_at = now
        await db.flush()
        return req

    # Check rejections
    if policy.max_rejections and req.rejections >= policy.max_rejections:
        req.state = "review_required"
        req.result_summary = f"Review required: {req.rejections} rejections"
        req.finalized_at = now
        await db.flush()
        return req

    # Check deadline
    if req.deadline_at <= now:
        req.state = policy.no_quorum_action
        req.result_summary = "No quorum by deadline"
        req.finalized_at = now
        await db.flush()
        return req

    return req
