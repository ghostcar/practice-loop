"""Personal Care — Join-table mutations and cycle snapshot."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.care import CareEntryProduct, CareRoutineProduct
from app.timeutils import local_today


async def set_entry_products(db: AsyncSession, entry_id: uuid.UUID, product_ids: list[uuid.UUID]) -> None:
    await db.execute(delete(CareEntryProduct).where(CareEntryProduct.entry_id == entry_id))
    for pid in product_ids:
        db.add(CareEntryProduct(entry_id=entry_id, product_id=pid))


async def set_routine_products(db: AsyncSession, routine_id: uuid.UUID, product_ids: list[uuid.UUID]) -> None:
    await db.execute(delete(CareRoutineProduct).where(CareRoutineProduct.routine_id == routine_id))
    for pid in product_ids:
        db.add(CareRoutineProduct(routine_id=routine_id, product_id=pid))


async def cycle_snapshot(db: AsyncSession, user_id: uuid.UUID, entry_date: date) -> tuple[str | None, int | None]:
    try:
        from app.api.health import _cycle_phase, _day_of_cycle
        from app.models.health import CycleEvent, CycleSettings
    except Exception:
        return None, None
    settings_row = (
        await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))
    ).scalar_one_or_none()
    events = (await db.execute(select(CycleEvent).where(CycleEvent.user_id == user_id))).scalars().all()
    day = _day_of_cycle(list(events), settings_row, entry_date)
    if day is None:
        return None, None
    phase = _cycle_phase(
        day,
        settings_row.cycle_length if settings_row else 28,
        settings_row.period_length if settings_row else 5,
    )
    return phase, day
