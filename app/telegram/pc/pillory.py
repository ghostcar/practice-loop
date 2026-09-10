"""Personal Contour — Pillory management & interaction (ADR-206 Stage 2 & 4).

Supports multi-trigger pillory entries, timer freeze escalation at 4+ extensions,
and autonomous media shame mode without an active lock session.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database import async_session_factory
from app.models.locktimer import LockSession
from app.models.pillory import PilloryEntry
from app.services.identity_service import get_active_tags
from app.services.pillory_service import (
    extend_pillory_entry,
    get_pillory_entry,
    list_active_pillory_entries,
    soften_pillory_entry,
    submit_repentance,
)
from app.telegram.pc.helpers import PersonalStates, _get_user_by_chat, _require_user, personal_router

logger = logging.getLogger(__name__)


@personal_router.message(F.text.in_(["⛓️ Позорный столб", "Позорный столб", "/pillory"]))
async def handle_pillory_tab(message: types.Message, state: FSMContext | None = None):
    if state is not None and getattr(state, "storage", None) is not None:
        await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    async with async_session_factory() as db:
        entries = await list_active_pillory_entries(db, user.id)

        # Check active lock session
        stmt = (
            select(LockSession)
            .where(LockSession.owner_id == user.id, LockSession.state.in_(["active", "locked", "frozen"]))
            .order_by(LockSession.created_at.desc())
        )
        session = (await db.execute(stmt)).scalars().first()

    tags = get_active_tags(user)
    has_legacy = session and (session.extensions_state or {}).get("is_pilloried")
    is_pilloried = bool(entries) or ("#pilloried" in tags) or has_legacy

    if not is_pilloried:
        lines = [
            "⛓️ **Позорный столб**\n",
            "🕊️ *Вы свободны и не находитесь на позорном столбе.*",
            "Ваша дисциплина не запятнана проступками.",
            "\n_Позорный столб активируется при нарушении проверок таймера, отказе от испытаний, секторе Колеса или по воле Ключника._",
        ]
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔒 К статусу пояса", callback_data="nav_wear")]]
        )
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
        return

    # Multi-entry pillory view
    now = datetime.now(UTC)
    lines = ["⛓️ **ВЫ НА ПОЗОРНОМ СТОЛБЕ** 💀\n"]

    if session and session.is_frozen:
        lines.append("❄️ **Таймер пояса заморожен** на всё время пребывания на столбе!\n")
    elif not session:
        lines.append("📢 **Автономный режим (без пояса):** статус `#pilloried` активен в профиле и сообществе.\n")

    inline_keyboard = []

    if entries:
        for idx, entry in enumerate(entries, 1):
            rem_sec = max(0, int((entry.expires_at - now).total_seconds()))
            rem_min = rem_sec // 60
            lines.append(f"📌 **Наказание #{idx}: {entry.title}**")
            lines.append(f"📋 *Причина:* _{entry.reason}_")
            lines.append(
                f"⏱ *Осталось:* {rem_min} мин (начальное: {entry.initial_duration_minutes} мин) | 🔄 Продлений: {entry.extensions_count}"
            )

            if entry.extensions_count >= 4:
                lines.append(
                    f"⚠️ *Эскалация:* 4+ продлений! Начислено штрафной заморозки: +{entry.freeze_timer_minutes} мин."
                )

            lines.append("")

            # Action buttons for this entry
            btn_extend = InlineKeyboardButton(
                text=f"⚡ Усилить #{idx} (+15м)",
                callback_data=f"pil_ext:{entry.id}",
            )
            btn_soften = InlineKeyboardButton(
                text=f"🕊 Смягчить #{idx} (-10м)",
                callback_data=f"pil_soft:{entry.id}",
            )
            inline_keyboard.append([btn_extend, btn_soften])
            inline_keyboard.append([
                InlineKeyboardButton(text=f"📸 Фото раскаяния #{idx}", callback_data=f"pil_rep:{entry.id}"),
                InlineKeyboardButton(text=f"⚖️ Снять (#{idx})", callback_data=f"pil_emul:{entry.id}"),
            ])
    else:
        # Fallback to single legacy session state
        ext = dict(session.extensions_state or {}) if session else {}
        reason = ext.get("pillory_reason", "Дисциплинарное нарушение")
        duration_min = ext.get("pillory_duration_minutes", 60)
        multiplier = ext.get("pillory_multiplier", 1.0)
        ext_count = ext.get("pillory_extensions_count", 0)

        lines.append(f"📋 **Причина наказания:** _{reason}_")
        lines.append(f"⏱ **Назначенное время:** {duration_min} мин (Множитель: ×{multiplier:g})")
        lines.append(f"🔄 **Продлений голосами:** {ext_count}")

        if ext_count >= 4:
            lines.append("⚠️ **Эскалация заморозки:** превышен порог 4 продлений!")

        inline_keyboard.append([
            InlineKeyboardButton(text="⚡ Усилить (+15м)", callback_data="pillory_extend"),
            InlineKeyboardButton(text="🕊 Смягчить (-10м)", callback_data="pillory_soften"),
        ])
        inline_keyboard.append([
            InlineKeyboardButton(text="📸 Сдать фото раскаяния", callback_data="pillory_repent"),
        ])

    inline_keyboard.append([InlineKeyboardButton(text="🔄 Обновить статус", callback_data="nav_pillory")])
    kb = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "nav_pillory")
async def cb_nav_pillory(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await handle_pillory_tab(callback.message, state)
    await callback.answer()


@personal_router.callback_query(F.data.startswith("pil_ext:"))
async def cb_pil_entry_extend(callback: types.CallbackQuery):
    entry_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        entry = await get_pillory_entry(db, uuid.UUID(entry_id_str), user.id)
        if entry is None:
            await callback.answer("Наказание не найдено или уже завершено.", show_alert=True)
            return

        res = await extend_pillory_entry(db, entry, user)
        await db.commit()

    msg = f"⚡ Наказание усилено на +{res['added_minutes']} мин!"
    if res.get("freeze_added_minutes", 0) > 0:
        msg += f"\n❄️ Подключена штрафная заморозка таймера (+{res['freeze_added_minutes']} мин)!"

    await callback.answer(msg, show_alert=True)
    await handle_pillory_tab(callback.message, None)


@personal_router.callback_query(F.data.startswith("pil_soft:"))
async def cb_pil_entry_soften(callback: types.CallbackQuery):
    entry_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        entry = await get_pillory_entry(db, uuid.UUID(entry_id_str), user.id)
        if entry is None:
            await callback.answer("Наказание не найдено.", show_alert=True)
            return

        res = await soften_pillory_entry(db, entry, user)
        await db.commit()

    await callback.answer(f"🕊 Наказание смягчено (-{res['subtracted_minutes']} мин).", show_alert=True)
    await handle_pillory_tab(callback.message, None)


@personal_router.callback_query(F.data.startswith("pil_emul:"))
async def cb_pil_entry_emulate(callback: types.CallbackQuery):
    """ADR-129 Voluntary Emulation: release pillory via digital autonomy."""
    entry_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        entry = await get_pillory_entry(db, uuid.UUID(entry_id_str), user.id)
        if entry is None:
            await callback.answer("Наказание не найдено.", show_alert=True)
            return

        await submit_repentance(db, entry, user, notes="Цифровая эмуляция (ADR-129)")
        await db.commit()

    await callback.answer("🕊 Наказание снято по праву цифровой автономии.", show_alert=True)
    await handle_pillory_tab(callback.message, None)


@personal_router.callback_query(F.data.startswith("pil_rep:"))
async def cb_pil_entry_repent(callback: types.CallbackQuery, state: FSMContext):
    entry_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    await state.set_state(PersonalStates.waiting_for_pillory_repentance_photo)
    await state.update_data(pillory_entry_id=entry_id_str)
    await callback.message.answer(
        "📸 *Фото раскаяния на Позорном столбе*\n\n"
        "Отправьте фотографию подтверждения смирения прямо в этот чат.\n"
        "Фото будет зафиксировано для досрочного снятия наказания.",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_pillory_repentance_photo, F.photo)
async def msg_pillory_photo(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        return

    data = await state.get_data()
    entry_id_str = data.get("pillory_entry_id")
    await state.clear()

    photo_id = message.photo[-1].file_id

    async with async_session_factory() as db:
        if entry_id_str:
            entry = await get_pillory_entry(db, uuid.UUID(entry_id_str), user.id)
            if entry:
                await submit_repentance(db, entry, user, photo_url=photo_id)
                await db.commit()
        else:
            # Legacy lock session support
            stmt = (
                select(LockSession)
                .where(LockSession.owner_id == user.id, LockSession.state.in_(["active", "locked", "frozen"]))
                .order_by(LockSession.created_at.desc())
            )
            session = (await db.execute(stmt)).scalars().first()
            if session:
                ext = dict(session.extensions_state or {})
                ext["repentance_submitted"] = True
                ext["pillory_duration_minutes"] = max(5, ext.get("pillory_duration_minutes", 60) // 2)
                session.extensions_state = ext
                session.row_version = (session.row_version or 0) + 1
                await db.commit()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⛓️ К позорному столбу", callback_data="nav_pillory")]]
    )
    await message.answer(
        "📸 *Фото раскаяния принято и зарегистрировано!*\n\n"
        "Позорный столб аннулирован либо срок сокращен в знак снисхождения.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# Legacy handlers preserved for backward compatibility
@personal_router.callback_query(F.data == "pillory_extend")
async def cb_pillory_extend_legacy(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        stmt = (
            select(LockSession)
            .where(LockSession.owner_id == user.id, LockSession.state.in_(["active", "locked", "frozen"]))
            .order_by(LockSession.created_at.desc())
        )
        session = (await db.execute(stmt)).scalars().first()
        if session:
            ext = dict(session.extensions_state or {})
            from app.services.discipline_engine import calc_effective_multiplier

            eff_mult = calc_effective_multiplier(user)
            mult = float(ext.get("pillory_multiplier", 1.0))
            added_min = int(round(15 * mult * eff_mult))
            ext["pillory_duration_minutes"] = ext.get("pillory_duration_minutes", 60) + added_min
            ext["pillory_extensions_count"] = ext.get("pillory_extensions_count", 0) + 1
            session.extensions_state = ext

            if ext["pillory_extensions_count"] >= 4:
                freeze_add = 600
                ext["freeze_penalty_seconds"] = ext.get("freeze_penalty_seconds", 0) + freeze_add
                if session.frozen_remaining_seconds:
                    session.frozen_remaining_seconds += freeze_add

            session.row_version = (session.row_version or 0) + 1
            await db.commit()

    await callback.answer(f"⚡ Наказание усилено на +{added_min} мин!", show_alert=True)
    await handle_pillory_tab(callback.message, None)


@personal_router.callback_query(F.data == "pillory_soften")
async def cb_pillory_soften_legacy(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        stmt = (
            select(LockSession)
            .where(LockSession.owner_id == user.id, LockSession.state.in_(["active", "locked", "frozen"]))
            .order_by(LockSession.created_at.desc())
        )
        session = (await db.execute(stmt)).scalars().first()
        if session:
            ext = dict(session.extensions_state or {})
            cur = ext.get("pillory_duration_minutes", 60)
            ext["pillory_duration_minutes"] = max(5, cur - 10)
            session.extensions_state = ext
            session.row_version = (session.row_version or 0) + 1
            await db.commit()

    await callback.answer("🕊 Смягчение принято (-10 мин).", show_alert=True)
    await handle_pillory_tab(callback.message, None)


@personal_router.callback_query(F.data == "pillory_repent")
async def cb_pillory_repent_legacy(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    await state.set_state(PersonalStates.waiting_for_pillory_repentance_photo)
    await callback.message.answer(
        "📸 *Фото раскаяния на Позорном столбе*\n\n"
        "Отправьте фотографию подтверждения смирения прямо в этот чат.\n"
        "Фото будет зафиксировано в журнале позора для смягчения наказания.",
        parse_mode="Markdown",
    )
    await callback.answer()


cb_pillory_extend = cb_pillory_extend_legacy
cb_pillory_soften = cb_pillory_soften_legacy
cb_pillory_repent = cb_pillory_repent_legacy
