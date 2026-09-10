"""Tests for Telegram bot Inventory, Pillory, and Medication restocking handlers (ADR-206)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.life import InventoryItem
from app.models.locktimer import LockSession
from app.models.medication import Medication, MedStock
from app.models.user import User
from app.telegram.pc.inventory import handle_inventory_tab, msg_seals_count
from app.telegram.pc.medications import msg_med_restock_qty
from app.telegram.pc.pillory import cb_pillory_extend, handle_pillory_tab


@pytest.mark.asyncio
async def test_inventory_tab_displays_seals_and_chastity(
    db_session: AsyncSession, test_user: User
) -> None:
    test_user.telegram_chat_id = 999111
    db_session.add(test_user)

    seal = InventoryItem(
        user_id=test_user.id,
        name="Красная пломба",
        category="seal",
        group_type="consumables",
        quantity=5,
        inventory_status="available",
    )
    belt = InventoryItem(
        user_id=test_user.id,
        name="Steel Cage v2",
        category="chastity",
        group_type="wear",
        quantity=1,
        inventory_status="in_use",
    )
    db_session.add_all([seal, belt])
    await db_session.commit()

    fake_msg = MagicMock()
    fake_msg.chat.id = 999111
    fake_msg.answer = AsyncMock()
    fake_state = AsyncMock()

    with (
        patch("app.telegram.pc.inventory._require_user", return_value=test_user),
        patch("app.telegram.pc.inventory._get_user_by_chat", return_value=test_user),
        patch("app.telegram.pc.inventory.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        await handle_inventory_tab(fake_msg, fake_state)

    fake_msg.answer.assert_awaited_once()
    called_text = fake_msg.answer.call_args[0][0]
    assert "5 шт." in called_text
    assert "Steel Cage v2" in called_text
    assert "надет" in called_text


@pytest.mark.asyncio
async def test_seals_restock_fsm(db_session: AsyncSession, test_user: User) -> None:
    test_user.telegram_chat_id = 999222
    db_session.add(test_user)
    await db_session.commit()

    fake_msg = MagicMock()
    fake_msg.chat.id = 999222
    fake_msg.text = "15"
    fake_msg.answer = AsyncMock()
    fake_state = AsyncMock()

    with (
        patch("app.telegram.pc.inventory._get_user_by_chat", return_value=test_user),
        patch("app.telegram.pc.inventory.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        await msg_seals_count(fake_msg, fake_state)

    fake_state.clear.assert_awaited_once()
    fake_msg.answer.assert_awaited_once()

    stmt = select(InventoryItem).where(InventoryItem.user_id == test_user.id, InventoryItem.category == "seal")
    item = (await db_session.execute(stmt)).scalar_one_or_none()
    assert item is not None
    assert item.quantity == 15


@pytest.mark.asyncio
async def test_medication_restock_fsm(db_session: AsyncSession, test_user: User) -> None:
    test_user.telegram_chat_id = 999333
    db_session.add(test_user)

    med = Medication(user_id=test_user.id, name="Эналаприл", unit="таб")
    db_session.add(med)
    await db_session.commit()

    fake_msg = MagicMock()
    fake_msg.chat.id = 999333
    fake_msg.text = "30"
    fake_msg.answer = AsyncMock()
    fake_state = AsyncMock()
    fake_state.get_data = AsyncMock(return_value={
        "restock_med_id": str(med.id),
        "restock_med_name": med.name,
        "restock_med_unit": med.unit,
    })

    with (
        patch("app.telegram.pc.medications._get_user_by_chat", return_value=test_user),
        patch("app.telegram.pc.medications.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        await msg_med_restock_qty(fake_msg, fake_state)

    fake_state.clear.assert_awaited_once()
    fake_msg.answer.assert_awaited_once()

    stmt = select(MedStock).where(MedStock.user_id == test_user.id, MedStock.medication_id == med.id)
    stock = (await db_session.execute(stmt)).scalar_one_or_none()
    assert stock is not None
    assert stock.quantity == 30.0


@pytest.mark.asyncio
async def test_pillory_tab_and_extension(db_session: AsyncSession, test_user: User) -> None:
    test_user.telegram_chat_id = 999444
    db_session.add(test_user)

    session = LockSession(
        owner_id=test_user.id,
        state="active",
        random_seed_encrypted="dummy_seed",
        random_seed_commitment="dummy_commit",
        is_frozen=False,
        extensions_state={"is_pilloried": True, "pillory_duration_minutes": 60, "pillory_multiplier": 1.0},
    )
    db_session.add(session)
    await db_session.commit()

    fake_msg = MagicMock()
    fake_msg.chat.id = 999444
    fake_msg.answer = AsyncMock()
    fake_state = AsyncMock()

    with (
        patch("app.telegram.pc.pillory._require_user", return_value=test_user),
        patch("app.telegram.pc.pillory._get_user_by_chat", return_value=test_user),
        patch("app.telegram.pc.pillory.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        await handle_pillory_tab(fake_msg, fake_state)

    fake_msg.answer.assert_awaited_once()
    text = fake_msg.answer.call_args[0][0]
    assert "позорном столбе" in text.lower()

    fake_cb = MagicMock()
    fake_cb.message.chat.id = 999444
    fake_cb.data = "pil_extend:15"
    fake_cb.answer = AsyncMock()
    fake_cb.message.delete = AsyncMock()
    fake_cb.message.answer = AsyncMock()

    with (
        patch("app.telegram.pc.pillory._require_user", return_value=test_user),
        patch("app.telegram.pc.pillory._get_user_by_chat", return_value=test_user),
        patch("app.telegram.pc.pillory.async_session_factory") as mock_af,
    ):
        mock_af.return_value.__aenter__.return_value = db_session
        await cb_pillory_extend(fake_cb)

    fake_cb.answer.assert_awaited_once()
    await db_session.refresh(session)
    ext = session.extensions_state or {}
    assert ext.get("pillory_duration_minutes") == 75
