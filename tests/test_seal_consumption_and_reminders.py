"""Tests for seal consumption and scheduled verification inspection reminders (ADR-206 Stage 5)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.life import InventoryItem
from app.models.locktimer import LockSession
from app.models.notification import Notification
from app.models.pillory import PilloryEntry
from app.models.user import User
from app.reminders.engine import collect_reminders
from app.services.wear_reactive_service import consume_seal_from_inventory, start_open_ended_session


@pytest.mark.asyncio
async def test_consume_seal_from_inventory(db_session: AsyncSession, test_user: User):
    """Verify seal consumption decrements inventory quantity and alerts on stock depletion."""
    seal = InventoryItem(
        user_id=test_user.id,
        name="Одноразовые номерные пломбы",
        category="chastity_seal",
        quantity=2,
        inventory_status="available",
    )
    db_session.add(seal)
    await db_session.flush()

    # First consumption: 2 -> 1
    res1 = await consume_seal_from_inventory(db_session, test_user.id, tag_number="SEAL-001")
    assert res1["consumed"] is True
    assert res1["remaining"] == 1
    assert seal.quantity == 1

    # Second consumption: 1 -> 0 (stock exhausted)
    res2 = await consume_seal_from_inventory(db_session, test_user.id, tag_number="SEAL-002")
    assert res2["consumed"] is True
    assert res2["remaining"] == 0
    assert seal.quantity == 0
    assert seal.inventory_status == "unavailable"

    # Notification created
    stmt = select(Notification).where(
        Notification.user_id == test_user.id,
        Notification.type == "inventory_low_stock",
    )
    notif = (await db_session.execute(stmt)).scalars().first()
    assert notif is not None
    assert "Закончились пломбы" in notif.title

    # Third attempt when quantity == 0
    res3 = await consume_seal_from_inventory(db_session, test_user.id, tag_number="SEAL-003")
    assert res3["consumed"] is False
    assert res3["remaining"] == 0


@pytest.mark.asyncio
async def test_start_session_consumes_seal(db_session: AsyncSession, test_user: User):
    """Verify starting open-ended session with tag automatically deducts seal from inventory."""
    seal = InventoryItem(
        user_id=test_user.id,
        name="Пломбы номерные СТ-10",
        category="seal",
        quantity=5,
        inventory_status="available",
    )
    db_session.add(seal)
    await db_session.flush()

    session, log = await start_open_ended_session(db_session, test_user.id, tag_number="TAG-7711")
    assert session.current_tag_number == "TAG-7711"
    assert seal.quantity == 4


@pytest.mark.asyncio
async def test_seal_stock_low_reminder(db_session: AsyncSession, test_user: User):
    """Verify daily reminder collection detects low seal stock (<= 2)."""
    seal = InventoryItem(
        user_id=test_user.id,
        name="Пломбы для пояса",
        category="chastity_seal",
        quantity=1,
        inventory_status="available",
    )
    db_session.add(seal)
    await db_session.flush()

    today = date.today()
    now = datetime.now(UTC)
    reminders = await collect_reminders(db_session, test_user.id, today, now, mode="daily")
    seal_rems = [r for r in reminders if r.kind == "seal_stock_low"]
    assert len(seal_rems) == 1
    assert "Запас пломб на исходе" in seal_rems[0].title


@pytest.mark.asyncio
async def test_wear_inspection_due_reminder_and_late_pillory(db_session: AsyncSession, test_user: User):
    """Verify event reminder generates inspection prompt and triggers pillory when overdue."""
    now = datetime.now(UTC)
    session = LockSession(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        state="active",
        mode="open_ended",
        is_currently_locked=True,
        current_tag_number="TAG-999",
        last_wear_checkin_at=now - timedelta(hours=5, minutes=45),  # 6h interval: 15m to due
        started_at=now - timedelta(hours=24),
        random_seed_encrypted="open_ended",
        random_seed_commitment="open_ended",
        pillory_enabled=True,
    )
    db_session.add(session)
    await db_session.flush()

    today = date.today()
    reminders = await collect_reminders(db_session, test_user.id, today, now, mode="event")
    inspect_rems = [r for r in reminders if r.kind == "wear_inspection_due"]
    assert len(inspect_rems) == 1
    assert "Контроль целостности пояса" in inspect_rems[0].title

    # Now simulate overdue by 8.5 hours (overdue by > 2 hours)
    session.last_wear_checkin_at = now - timedelta(hours=8, minutes=30)
    await db_session.flush()

    await collect_reminders(db_session, test_user.id, today, now, mode="event")

    # PilloryEntry should be created for late check
    stmt = select(PilloryEntry).where(
        PilloryEntry.user_id == test_user.id,
        PilloryEntry.trigger == "late_check",
    )
    entry = (await db_session.execute(stmt)).scalars().first()
    assert entry is not None
    assert entry.status == "active"
    assert "Просрочка инспекции" in entry.title
