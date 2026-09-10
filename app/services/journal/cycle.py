"""Sexual Journal — Cycle snapshot and timer bridge."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import JournalEntry


async def cycle_snapshot(db: AsyncSession, user_id: uuid.UUID, entry_date: date) -> tuple[str | None, int | None]:
    try:
        from app.models.health import CycleEvent, CycleSettings
        from app.services.health_service import cycle_phase as _cycle_phase
        from app.services.health_service import day_of_cycle as _day_of_cycle
    except Exception:
        return None, None
    settings_row = (
        await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))
    ).scalar_one_or_none()
    events = (await db.execute(select(CycleEvent).where(CycleEvent.user_id == user_id))).scalars().all()
    day = _day_of_cycle(list(events), settings_row, entry_date)
    if day is None:
        return None, None
    ph = _cycle_phase(
        day,
        settings_row.cycle_length if settings_row else 28,
        settings_row.period_length if settings_row else 5,
    )
    return ph, day


async def ensure_timer_slot_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    slot_occurrence_id: uuid.UUID,
    entry_date: date,
) -> JournalEntry | None:
    existing = (
        await db.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == user_id,
                JournalEntry.slot_occurrence_id == slot_occurrence_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    cycle_ph, cycle_day = await cycle_snapshot(db, user_id, entry_date)
    entry = JournalEntry(
        user_id=user_id,
        entry_date=entry_date,
        status="draft",
        source="timer_slot",
        timer_session_id=session_id,
        slot_occurrence_id=slot_occurrence_id,
        cycle_phase=cycle_ph,
        cycle_day=cycle_day,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_pending_slot_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    slot_occurrence_id: uuid.UUID,
) -> JournalEntry | None:
    return (
        await db.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == user_id,
                JournalEntry.slot_occurrence_id == slot_occurrence_id,
                JournalEntry.status == "draft",
            )
        )
    ).scalar_one_or_none()
