"""Personal Contour — Progress & Gamification."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database import async_session_factory
from app.models.points import PenaltyRedemption, PointsTransaction
from app.models.progress import UserProgress
from app.models.quest import UserQuest
from app.prefs import prefs_from_dict
from app.services.identity_registry import PRIMARY_ROLES
from app.services.identity_service import get_active_tags, get_effective_display_name
from app.telegram.keyboards import get_stats_keyboard
from app.telegram.pc.helpers import _get_user_by_chat, _require_user, personal_router


@personal_router.message(F.text.in_(["🏆 Прогресс", "Прогресс", "/stats", "/profile"]))
async def handle_stats_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    async with async_session_factory() as db:
        progress = (
            await db.execute(select(UserProgress).where(UserProgress.user_id == user.id))
        ).scalar_one_or_none()

        pen_stmt = select(PenaltyRedemption).where(
            PenaltyRedemption.user_id == user.id,
            PenaltyRedemption.status == "pending",
        )
        penalties = (await db.execute(pen_stmt)).scalars().all()

        quests_stmt = select(UserQuest).where(
            UserQuest.user_id == user.id,
            UserQuest.status == "active",
        )
        quests = (await db.execute(quests_stmt)).scalars().all()

    if not progress:
        await message.answer("📊 У вас пока нет статистики. Выполните вашу первую практику!")
        return

    has_penalties = len(penalties) > 0

    is_discretion = prefs_from_dict(user.prefs).discretion_active_at()
    eff_name = get_effective_display_name(user, discretion_active=is_discretion)

    lines = [
        f"🏆 *Профиль:* {eff_name}",
    ]

    if not is_discretion:
        role_meta = PRIMARY_ROLES.get(user.primary_role or "submissive", {})
        role_title = role_meta.get("title_ru", user.primary_role or "Ведомый")
        lines.append(f"🎭 Роль: *{role_title}*")

        active_tags = get_active_tags(user)
        if active_tags:
            tags_str = " ".join(f"`{t}`" for t in active_tags)
            lines.append(f"🏷 Статус-теги: {tags_str}")

        if user.ai_identity_locked:
            lines.append("🔒 _Идентичность зафиксирована алгоритмом ИИ_")

    lines.extend([
        f"\n⭐ Уровень: *{progress.level}* ({progress.xp} XP)",
        f"🔥 Серия дней подряд: *{progress.current_streak}* (рекорд: {progress.longest_streak})",
        f"💰 Баланс баллов: *{progress.points_balance}*",
        f"✅ Всего завершено практик: *{progress.total_completed}*",
        f"⏹ Прервано: *{progress.total_interrupted}*",
    ])

    if has_penalties:
        lines.append(f"\n⚠️ *Активные штрафы к отработке:* {len(penalties)} шт.")
        total_pen = sum(p.points_value for p in penalties)
        lines.append(f"Можно вернуть: *+{total_pen}* баллов через отработку.")

    if quests:
        lines.append(f"\n🎯 *Активных квестов:* {len(quests)}")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_stats_keyboard(has_penalties=has_penalties),
    )


@personal_router.callback_query(F.data == "stat_refresh")
async def cb_stat_refresh(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await handle_stats_tab(callback.message, state)
    await callback.answer("Обновлено")


@personal_router.callback_query(F.data == "stat_redemptions")
async def cb_stat_redemptions(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        pen_stmt = (
            select(PenaltyRedemption)
            .where(PenaltyRedemption.user_id == user.id, PenaltyRedemption.status == "pending")
            .order_by(PenaltyRedemption.created_at.desc())
            .limit(5)
        )
        penalties = (await db.execute(pen_stmt)).scalars().all()

    if not penalties:
        await callback.answer("Штрафов к отработке нет! 🎉", show_alert=True)
        return

    lines = ["🔄 *Отработка штрафов (Penalty Redemptions)*\n"]
    rows: list[list[InlineKeyboardButton]] = []

    for p in penalties:
        desc = p.description or p.redemption_type or "Отработка"
        pts = p.points_value
        lines.append(f"• **{desc}** (+{pts} баллов)")
        rows.append([
            InlineKeyboardButton(
                text=f"✅ Отработать: {desc[:20]} (+{pts})",
                callback_data=f"redemp_do:{p.id}",
            )
        ])

    rows.append([InlineKeyboardButton(text="🏆 Назад к прогрессу", callback_data="stat_refresh")])
    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@personal_router.callback_query(F.data.startswith("redemp_do:"))
async def cb_redemp_do(callback: types.CallbackQuery):
    redemp_id = uuid.UUID(callback.data.split(":", 1)[1])
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        redemp = (
            await db.execute(
                select(PenaltyRedemption).where(
                    PenaltyRedemption.id == redemp_id,
                    PenaltyRedemption.user_id == user.id,
                )
            )
        ).scalar_one_or_none()

        if not redemp or redemp.status != "pending":
            await callback.answer("Штраф не найден или уже отработан.", show_alert=True)
            return

        redemp.status = "completed"
        redemp.completed_at = datetime.now(UTC)

        progress = (await db.execute(select(UserProgress).where(UserProgress.user_id == user.id))).scalar_one_or_none()
        if progress:
            progress.points_balance += redemp.points_value

        tx = PointsTransaction(
            user_id=user.id,
            amount=redemp.points_value,
            transaction_type="bonus",
            description=f"Штраф отработан: {redemp.description or redemp.redemption_type}",
        )
        db.add(tx)
        await db.commit()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏆 К прогрессу", callback_data="stat_refresh")]]
    )
    await callback.message.edit_text(
        f"🎉 **Штраф успешно отработан!**\n"
        f"💰 На ваш баланс возвращено: *+{redemp.points_value}* баллов.",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Отработано! Баллы возвращены 🎉")


@personal_router.callback_query(F.data == "stat_quests")
async def cb_stat_quests(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        stmt = (
            select(UserQuest)
            .where(UserQuest.user_id == user.id, UserQuest.status == "active")
            .limit(5)
        )
        quests = (await db.execute(stmt)).scalars().all()

    lines = ["🎯 *Текущие квесты и челленджи*\n"]
    if not quests:
        lines.append("Нет активных квестов на сегодня. Загляните на сайт в раздел Достижения!")
    else:
        for uq in quests:
            q = uq.quest
            title = q.title if q else "Квест"
            target = q.target_count if q else 1
            reward = q.reward_xp if q else 100
            lines.append(f"• **{title}**: {uq.current_progress}/{target} (Награда: ⭐ {reward} XP)")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏆 Назад", callback_data="stat_refresh")]]
    )
    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
    await callback.answer()
