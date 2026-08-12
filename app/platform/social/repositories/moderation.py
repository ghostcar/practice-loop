"""Social moderation — reports, actions, content hiding (S5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social.models import (
    ModerationAction,
    ModerationReport,
    SocialComment,
    SocialPublication,
    SocialVerificationRequest,
    SocialVerificationVote,
)


async def create_report(
    db: AsyncSession,
    reporter_id: uuid.UUID | None,
    target_type: str,
    target_id: uuid.UUID,
    reason_code: str,
    details: str | None = None,
) -> ModerationReport:
    """File an abuse report. Reporter identity is protected — never exposed to target."""
    report = ModerationReport(
        reporter_id=reporter_id,
        target_type=target_type,
        target_id=target_id,
        reason_code=reason_code,
        details=details,
    )
    db.add(report)
    await db.flush()
    return report


async def get_report(db: AsyncSession, report_id: uuid.UUID) -> ModerationReport | None:
    result = await db.execute(select(ModerationReport).where(ModerationReport.id == report_id))
    return result.scalar_one_or_none()


async def list_reports(
    db: AsyncSession,
    *,
    state: str | None = None,
    target_type: str | None = None,
    limit: int = 50,
) -> list[ModerationReport]:
    """List reports for moderator queue. Filterable by state and target_type."""
    stmt = select(ModerationReport).order_by(ModerationReport.created_at.desc()).limit(limit)
    if state:
        stmt = stmt.where(ModerationReport.state == state)
    if target_type:
        stmt = stmt.where(ModerationReport.target_type == target_type)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def assign_report(
    db: AsyncSession,
    report_id: uuid.UUID,
    moderator_id: uuid.UUID,
) -> ModerationReport | None:
    report = await get_report(db, report_id)
    if report is None:
        return None
    report.assigned_to = moderator_id
    report.state = "reviewing"
    report.updated_at = datetime.utcnow()
    await db.flush()
    return report


async def resolve_report(
    db: AsyncSession,
    report_id: uuid.UUID,
    moderator_id: uuid.UUID,
) -> ModerationReport | None:
    report = await get_report(db, report_id)
    if report is None:
        return None
    report.state = "resolved"
    report.assigned_to = moderator_id
    report.updated_at = datetime.utcnow()
    await db.flush()
    return report


async def dismiss_report(
    db: AsyncSession,
    report_id: uuid.UUID,
    moderator_id: uuid.UUID,
) -> ModerationReport | None:
    report = await get_report(db, report_id)
    if report is None:
        return None
    report.state = "dismissed"
    report.assigned_to = moderator_id
    report.updated_at = datetime.utcnow()
    await db.flush()
    return report


async def create_moderation_action(
    db: AsyncSession,
    report_id: uuid.UUID,
    moderator_id: uuid.UUID,
    action_type: str,
    reason: str,
    action_metadata: dict | None = None,
) -> ModerationAction:
    """Record an immutable moderation action (append-only audit trail)."""
    action = ModerationAction(
        report_id=report_id,
        moderator_id=moderator_id,
        action_type=action_type,
        reason=reason,
        action_metadata=action_metadata or {},
    )
    db.add(action)
    await db.flush()
    return action


async def list_moderation_actions(
    db: AsyncSession,
    report_id: uuid.UUID,
) -> list[ModerationAction]:
    result = await db.execute(
        select(ModerationAction)
        .where(ModerationAction.report_id == report_id)
        .order_by(ModerationAction.created_at.asc())
    )
    return list(result.scalars().all())


async def hide_publication(
    db: AsyncSession,
    publication_id: uuid.UUID,
) -> bool:
    """Moderation: hide a publication from feed."""
    result = await db.execute(
        select(SocialPublication).where(
            SocialPublication.id == publication_id,
            SocialPublication.is_active,
        )
    )
    pub = result.scalar_one_or_none()
    if pub is None:
        return False
    pub.is_active = False
    pub.withdrawn_at = datetime.utcnow()
    await db.flush()
    return True


async def hide_comment(
    db: AsyncSession,
    comment_id: uuid.UUID,
) -> bool:
    """Moderation: hide a comment (set body to '[removed by moderation]')."""
    result = await db.execute(select(SocialComment).where(SocialComment.id == comment_id))
    comment = result.scalar_one_or_none()
    if comment is None:
        return False
    comment.body = "[removed by moderation]"
    comment.is_edited = True
    comment.edited_at = datetime.utcnow()
    await db.flush()
    return True


async def invalidate_vote(
    db: AsyncSession,
    vote_id: uuid.UUID,
) -> bool:
    """Moderation: invalidate a verification vote (delete it, adjust counters)."""
    result = await db.execute(select(SocialVerificationVote).where(SocialVerificationVote.id == vote_id))
    vote = result.scalar_one_or_none()
    if vote is None:
        return False

    # Adjust the request counters
    req_result = await db.execute(
        select(SocialVerificationRequest).where(
            SocialVerificationRequest.id == vote.request_id,
            SocialVerificationRequest.state == "open",
        )
    )
    req = req_result.scalar_one_or_none()
    if req is not None:
        if vote.value == "approve" and req.approvals > 0:
            req.approvals -= 1
        elif vote.value == "reject" and req.rejections > 0:
            req.rejections -= 1

    await db.delete(vote)
    await db.flush()
    return True
