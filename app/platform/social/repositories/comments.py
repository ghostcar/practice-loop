"""Social comments + encouragements (S4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social.models import SocialComment, SocialEncouragement


async def create_comment(
    db: AsyncSession,
    author_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    body: str,
) -> SocialComment:
    comment = SocialComment(
        author_id=author_id,
        target_type=target_type,
        target_id=target_id,
        body=body,
    )
    db.add(comment)
    await db.flush()
    return comment


async def edit_comment(
    db: AsyncSession,
    comment_id: uuid.UUID,
    author_id: uuid.UUID,
    body: str,
) -> SocialComment | None:
    result = await db.execute(
        select(SocialComment).where(
            SocialComment.id == comment_id,
            SocialComment.author_id == author_id,
        )
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        return None
    comment.body = body
    comment.is_edited = True
    comment.edited_at = datetime.now(UTC)
    await db.flush()
    return comment


async def delete_comment(
    db: AsyncSession,
    comment_id: uuid.UUID,
    author_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(SocialComment).where(
            SocialComment.id == comment_id,
            SocialComment.author_id == author_id,
        )
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        return False
    await db.delete(comment)
    await db.flush()
    return True


async def list_comments(
    db: AsyncSession,
    target_type: str,
    target_id: uuid.UUID,
) -> list[SocialComment]:
    result = await db.execute(
        select(SocialComment)
        .where(SocialComment.target_type == target_type, SocialComment.target_id == target_id)
        .order_by(SocialComment.created_at.asc())
    )
    return list(result.scalars().all())


async def create_encouragement(
    db: AsyncSession,
    sender_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    encouragement_type: str,
) -> SocialEncouragement | None:
    enc = SocialEncouragement(
        sender_id=sender_id,
        target_type=target_type,
        target_id=target_id,
        encouragement_type=encouragement_type,
    )
    try:
        async with db.begin_nested():
            db.add(enc)
            await db.flush()
    except IntegrityError:
        # The database uniqueness constraint is the concurrency-safe
        # idempotency boundary.  Roll back only the savepoint so the caller's
        # request transaction remains usable.
        return None
    return enc
