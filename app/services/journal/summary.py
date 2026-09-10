"""Sexual Journal — Summary, media, activity title map."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import JournalEntry
from app.models.media import MediaAsset
from app.timeutils import local_today


async def journal_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    today = local_today()
    since = today - timedelta(days=30)
    rows = (
        (
            await db.execute(
                select(JournalEntry)
                .where(JournalEntry.user_id == user_id, JournalEntry.entry_date >= since)
                .order_by(JournalEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    total = (await db.execute(select(func.count(JournalEntry.id)).where(JournalEntry.user_id == user_id))).scalar() or 0
    pending = (
        await db.execute(
            select(func.count(JournalEntry.id)).where(JournalEntry.user_id == user_id, JournalEntry.status == "draft")
        )
    ).scalar() or 0
    satisfactions = [r.satisfaction for r in rows if r.satisfaction is not None]
    last = rows[0] if rows else None
    return {
        "count_30d": len(rows),
        "total": total,
        "pending": pending,
        "last_date": last.entry_date.isoformat() if last else None,
        "last_type": last.activity_type if last else None,
        "avg_satisfaction": round(sum(satisfactions) / len(satisfactions), 1) if satisfactions else None,
    }


async def media_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, list[dict]]:
    rows = (
        (
            await db.execute(
                select(MediaAsset)
                .where(MediaAsset.owner_id == user_id, MediaAsset.owner_type == "journal_entry")
                .order_by(MediaAsset.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, list[dict]] = {}
    for a in rows:
        key = str(a.owner_ref_id) if a.owner_ref_id else ""
        if not key:
            continue
        out.setdefault(key, []).append(
            {
                "id": str(a.id),
                "has_thumbnail": a.thumbnail_path is not None,
                "is_image": (a.mime_type or "").startswith("image/"),
                "caption": a.caption,
            }
        )
    return out


async def activity_title_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    from app.models.activity_log import ActivityLog

    ids = (
        (
            await db.execute(
                select(JournalEntry.activity_log_id).where(
                    JournalEntry.user_id == user_id, JournalEntry.activity_log_id.is_not(None)
                )
            )
        )
        .scalars()
        .all()
    )
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    rows = (await db.execute(select(ActivityLog).where(ActivityLog.id.in_(ids)))).scalars().all()
    return {str(r.id): (r.title_override or r.selected_entity_name or str(r.id)[:8]) for r in rows}
