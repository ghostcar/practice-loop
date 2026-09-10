"""Tests for medication stock control and reminder isolation (ADR-206 Stage 1).

Verifies:
1. Catalog-only medication (without active schedule/course) never produces
   low-stock or intake reminders, even if MedStock quantity is 0.
2. Scheduled medication with 0 stock produces out-of-stock notification instead
   of med_due/med_dose.
3. Scheduled medication with positive stock produces regular med_due.
4. create_medication does not auto-create schedule from instructions unless
   auto_schedule=True.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import Medication, MedSchedule, MedStock
from app.models.user import User
from app.reminders.engine import collect_reminders
from app.services.med.crud import create_medication


@pytest.mark.asyncio
async def test_passive_catalog_medication_no_reminders(db_session: AsyncSession, test_user: User) -> None:
    # 1. User simply adds a medication to directory
    med = Medication(user_id=test_user.id, name="Test Catalog Drug", kind="medication")
    db_session.add(med)
    await db_session.flush()

    # Even with an empty MedStock (quantity=0, low_stock_threshold=5.0)
    stock = MedStock(user_id=test_user.id, medication_id=med.id, quantity=0.0, low_stock_threshold=5.0)
    db_session.add(stock)
    await db_session.flush()

    today = date.today()
    now = datetime.now(UTC)

    # Daily batch
    reminders = await collect_reminders(db_session, test_user.id, today, now, mode="daily")
    med_reminders = [r for r in reminders if r.kind.startswith("med_")]
    assert len(med_reminders) == 0, f"Expected no med reminders for catalog-only drug, got: {med_reminders}"


@pytest.mark.asyncio
async def test_scheduled_medication_with_zero_stock_produces_out_of_stock(
    db_session: AsyncSession, test_user: User
) -> None:
    med = Medication(user_id=test_user.id, name="Prescribed Antibiotic", kind="medication")
    db_session.add(med)
    await db_session.flush()

    sched = MedSchedule(
        user_id=test_user.id,
        medication_id=med.id,
        dose_quantity=1.0,
        frequency_type="daily",
        times_per_day=1,
        times_of_day=["09:00"],
        is_active=True,
    )
    db_session.add(sched)

    stock = MedStock(user_id=test_user.id, medication_id=med.id, quantity=0.0, low_stock_threshold=5.0)
    db_session.add(stock)
    await db_session.flush()

    today = date.today()
    now = datetime.now(UTC)

    reminders = await collect_reminders(db_session, test_user.id, today, now, mode="daily")
    assert not any(r.kind == "med_due" for r in reminders), "Should not ask to take dose when stock is 0"
    out_of_stock = [r for r in reminders if r.kind == "med_out_of_stock"]
    assert len(out_of_stock) == 1
    assert "Закончился препарат" in out_of_stock[0].title or "Prescribed Antibiotic" in out_of_stock[0].title


@pytest.mark.asyncio
async def test_scheduled_medication_with_positive_stock_produces_med_due(
    db_session: AsyncSession, test_user: User
) -> None:
    med = Medication(user_id=test_user.id, name="Daily Vitamin", kind="supplement")
    db_session.add(med)
    await db_session.flush()

    sched = MedSchedule(
        user_id=test_user.id,
        medication_id=med.id,
        dose_quantity=1.0,
        frequency_type="daily",
        times_per_day=1,
        is_active=True,
    )
    db_session.add(sched)

    stock = MedStock(user_id=test_user.id, medication_id=med.id, quantity=20.0, low_stock_threshold=5.0)
    db_session.add(stock)
    await db_session.flush()

    today = date.today()
    now = datetime.now(UTC)

    reminders = await collect_reminders(db_session, test_user.id, today, now, mode="daily")
    assert any(r.kind == "med_due" for r in reminders)
    assert not any(r.kind == "med_out_of_stock" for r in reminders)


@pytest.mark.asyncio
async def test_create_medication_auto_schedule_guard(db_session: AsyncSession, test_user: User) -> None:
    # Adding medication with instructions without auto_schedule should NOT create a schedule
    m1 = await create_medication(
        db_session,
        user_id=test_user.id,
        name="Aspirin 500",
        kind="medication",
        active_ingredient="Acetylsalicylic acid",
        form="tablets",
        strength="500mg",
        manufacturer="Bayer",
        storage_conditions="dry",
        prescription_required=False,
        unit="tab",
        instructions="Принимать по 1 таблетке в день",
        notes="",
        auto_schedule=False,
    )
    schedules1 = (
        (await db_session.execute(select(MedSchedule).where(MedSchedule.medication_id == m1.id))).scalars().all()
    )
    assert len(schedules1) == 0, "No schedule should be created when auto_schedule=False"

    # With auto_schedule=True, it creates the schedule
    m2 = await create_medication(
        db_session,
        user_id=test_user.id,
        name="Ibuprofen 400",
        kind="medication",
        active_ingredient="Ibuprofen",
        form="tablets",
        strength="400mg",
        manufacturer="Pharm",
        storage_conditions="dry",
        prescription_required=False,
        unit="tab",
        instructions="1 таблетка 1 раз в день",
        notes="",
        auto_schedule=True,
    )
    schedules2 = (
        (await db_session.execute(select(MedSchedule).where(MedSchedule.medication_id == m2.id))).scalars().all()
    )
    assert len(schedules2) == 1, "Schedule should be created when auto_schedule=True"
