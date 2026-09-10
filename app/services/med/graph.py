"""Graph loading (selectinload) and lookups."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.medication import (
    MedComponent,
    Medication,
    MedKit,
    MedSchedule,
    MedStock,
)
from app.services.errors import NotFoundError


async def load_meds_graph(db: AsyncSession, user_id: uuid.UUID) -> list[Medication]:
    """Все препараты пользователя с компонентами/веществами/вариантами."""
    return (
        (
            await db.execute(
                select(Medication)
                .where(Medication.user_id == user_id)
                .options(
                    selectinload(Medication.components).selectinload(MedComponent.substance),
                    selectinload(Medication.components).selectinload(MedComponent.variant),
                    selectinload(Medication.variants),
                )
            )
        )
        .scalars()
        .all()
    )


async def get_med(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> Medication:
    m = (
        await db.execute(select(Medication).where(Medication.id == medication_id, Medication.user_id == user_id))
    ).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Medication not found")
    return m


def med_matches_query(m: Medication, ql: str) -> bool:
    """Быстрый поиск по имени/торговому названию/составу."""
    name = (m.name or "").lower()
    ingredient = (m.active_ingredient or "").lower()
    form = (m.form or "").lower()
    return ql in name or ql in ingredient or ql in form


async def get_kit(db: AsyncSession, user_id: uuid.UUID, kit_id: uuid.UUID) -> MedKit:
    k = (
        await db.execute(select(MedKit).where(MedKit.id == kit_id, MedKit.user_id == user_id))
    ).scalar_one_or_none()
    if k is None:
        raise NotFoundError("Kit not found")
    return k


async def get_schedule(db: AsyncSession, user_id: uuid.UUID, schedule_id: uuid.UUID) -> MedSchedule:
    s = (
        await db.execute(select(MedSchedule).where(MedSchedule.id == schedule_id, MedSchedule.user_id == user_id))
    ).scalar_one_or_none()
    if s is None:
        raise NotFoundError("Schedule not found")
    return s


async def get_stock(db: AsyncSession, user_id: uuid.UUID, stock_id: uuid.UUID) -> MedStock:
    st = (
        await db.execute(select(MedStock).where(MedStock.id == stock_id, MedStock.user_id == user_id))
    ).scalar_one_or_none()
    if st is None:
        raise NotFoundError("Stock not found")
    return st


async def _reload_med_graph(db: AsyncSession, m: Medication) -> Medication:
    """Перечитать препарат с составом и вариантами (async selectinload)."""
    return (
        await db.execute(
            select(Medication)
            .where(Medication.id == m.id)
            .options(
                selectinload(Medication.components).selectinload(MedComponent.substance),
                selectinload(Medication.components).selectinload(MedComponent.variant),
                selectinload(Medication.variants),
            )
        )
    ).scalar_one()
