"""Personal Contour — Inventory & Seals management (ADR-206 Stage 2)."""

from __future__ import annotations

import logging

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import or_, select

from app.database import async_session_factory
from app.models.life import InventoryItem
from app.telegram.pc.helpers import PersonalStates, _get_user_by_chat, _require_user, personal_router

logger = logging.getLogger(__name__)


@personal_router.message(F.text.in_(["📦 Инвентарь", "Инвентарь", "/inventory", "/inv"]))
async def handle_inventory_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    async with async_session_factory() as db:
        stmt = (
            select(InventoryItem)
            .where(
                InventoryItem.user_id == user.id,
                InventoryItem.migrated_to_medication.is_(False),
                InventoryItem.inventory_status != "archived",
            )
            .order_by(InventoryItem.category, InventoryItem.name)
        )
        items = (await db.execute(stmt)).scalars().all()

    seals = [it for it in items if it.category == "seal" or "пломб" in it.name.lower()]
    chastity = [
        it for it in items
        if it.category == "chastity" or "пояс" in it.name.lower() or "замок" in it.name.lower()
    ]
    others = [it for it in items if it not in seals and it not in chastity]

    lines = ["📦 *Инвентарь и снаряжение*\n"]

    # 1. Seals section
    total_seals = sum(it.quantity for it in seals)
    if seals:
        if total_seals > 2:
            seal_status = "🟢 В наличии"
        elif total_seals > 0:
            seal_status = "⚠️ Заканчиваются"
        else:
            seal_status = "🔴 Закончились"
        lines.append(f"🏷️ *Номерные пломбы:* **{total_seals} шт.** ({seal_status})")
        for s in seals[:3]:
            lines.append(f"  • {s.name}: {s.quantity} шт.")
    else:
        lines.append("🏷️ *Номерные пломбы:* _нет записей_")

    # 2. Devices section
    if chastity:
        lines.append(f"\n🔒 *Устройства поясов верности ({len(chastity)}):*")
        for d in chastity:
            st_icon = "🟢" if d.inventory_status == "available" else ("🔒" if d.inventory_status == "in_use" else "⏳")
            status_text = (
                "свободен"
                if d.inventory_status == "available"
                else ("надет" if d.inventory_status == "in_use" else d.inventory_status)
            )
            lines.append(f"  • {st_icon} *{d.name}* ({status_text})")
    else:
        lines.append("\n🔒 *Устройства:* _не добавлены_")

    # 3. Other equipment
    if others:
        lines.append(f"\n🎒 *Прочее снаряжение ({len(others)}):*")
        for o in others[:5]:
            lines.append(f"  • {o.name} ({o.quantity} шт.)")
        if len(others) > 5:
            lines.append(f"  _...и ещё {len(others) - 5} предм._")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏷️ ➕ Пополнить пломбы", callback_data="inv_restock_seals"),
            ],
            [
                InlineKeyboardButton(text="➕ Добавить предмет", callback_data="inv_add_item"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data="nav_inventory"),
            ],
        ]
    )
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "nav_inventory")
async def cb_nav_inventory(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await handle_inventory_tab(callback.message, state)
    await callback.answer()


@personal_router.callback_query(F.data == "inv_restock_seals")
async def cb_inv_restock_seals(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    await state.set_state(PersonalStates.waiting_for_seals_count)
    await callback.message.answer(
        "🏷️ *Пополнение запаса пломб*\n\n"
        "Сколько пломб вы хотите добавить?\n"
        "Отправьте число (например: `10` или `25`):",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_seals_count)
async def msg_seals_count(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        return

    text = (message.text or "").strip()
    try:
        count = int(text)
        if count <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите положительное целое число (например, `10`).", parse_mode="Markdown")
        return

    await state.clear()
    async with async_session_factory() as db:
        stmt = select(InventoryItem).where(
            InventoryItem.user_id == user.id,
            or_(InventoryItem.category == "seal", InventoryItem.name.ilike("%пломб%")),
        )
        item = (await db.execute(stmt)).scalars().first()
        if item:
            item.quantity += count
            item.inventory_status = "available"
        else:
            item = InventoryItem(
                user_id=user.id,
                name="Номерные пломбы",
                category="seal",
                group_type="equipment",
                quantity=count,
                inventory_status="available",
            )
            db.add(item)
        await db.commit()
        total = item.quantity

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📦 К инвентарю", callback_data="nav_inventory")]]
    )
    await message.answer(
        f"✅ *Запас пломб успешно пополнен!*\n\n"
        f"Добавлено: **+{count} шт.**\n"
        f"Текущий остаток в наличии: **{total} шт.**",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@personal_router.callback_query(F.data == "inv_add_item")
async def cb_inv_add_item(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    await state.set_state(PersonalStates.waiting_for_item_name)
    await callback.message.answer(
        "➕ *Добавление предмета в инвентарь*\n\n"
        "Отправьте название предмета (например: `Пояс SteelLock v2` или `Пластиковая пломба Seal-T`):",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_item_name)
async def msg_inv_item_name(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        return

    name = (message.text or "").strip()
    if not name or len(name) < 2:
        await message.answer("⚠️ Название предмета слишком короткое. Попробуйте ещё раз:")
        return

    await state.clear()
    name_lower = name.lower()
    if "пломб" in name_lower:
        cat = "seal"
    elif any(w in name_lower for w in ["пояс", "замок", "клетка", "chastity"]):
        cat = "chastity"
    else:
        cat = "equipment"
    group = "wear" if cat == "chastity" else "equipment"

    async with async_session_factory() as db:
        item = InventoryItem(
            user_id=user.id,
            name=name[:300],
            category=cat,
            group_type=group,
            quantity=1,
            inventory_status="available",
        )
        db.add(item)
        await db.commit()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📦 К инвентарю", callback_data="nav_inventory")]]
    )
    await message.answer(
        f"✅ Предмет **{name}** добавлен в инвентарь (категория: `{cat}`)!",
        parse_mode="Markdown",
        reply_markup=kb,
    )
