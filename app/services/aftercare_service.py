"""Aftercare Service — business logic from app.api.aftercare."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aftercare import AftercareEntry

AFTERCARE_KINDS = ("physical", "emotional", "debrief", "hydration", "rest", "other")


async def aftercare_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Dashboard summary: entries in 30d / last entry / kinds count. Relief-only."""
    rows = (
        (
            await db.execute(
                select(AftercareEntry)
                .where(AftercareEntry.user_id == user_id)
                .order_by(AftercareEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    last = None
    if rows:
        r = rows[0]
        last = {"entry_date": r.entry_date.isoformat(), "kind": r.kind, "notes": r.notes}
    return {
        "total": len(rows),
        "last": last,
        "kinds": {k: sum(1 for r in rows if r.kind == k) for k in AFTERCARE_KINDS},
    }


async def get_aftercare_page_context(db: AsyncSession, user_id: uuid.UUID):
    rows = (
        (
            await db.execute(
                select(AftercareEntry)
                .where(AftercareEntry.user_id == user_id)
                .order_by(AftercareEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"entries": rows, "kinds": AFTERCARE_KINDS}


async def create_entry(db: AsyncSession, user_id: uuid.UUID, **kwargs) -> AftercareEntry:
    kwargs.setdefault("entry_date", date.today())
    entry = AftercareEntry(user_id=user_id, **kwargs)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


async def delete_entry(db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID):
    entry = (
        await db.execute(
            select(AftercareEntry).where(
                AftercareEntry.id == entry_id,
                AftercareEntry.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if not entry:
        raise ValueError("Entry not found")
    await db.delete(entry)
