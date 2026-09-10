"""Personal Contour — Today's Tasks & Execution."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from app.database import async_session_factory
from app.gamification.handler import on_task_completed, on_task_interrupted
from app.models.activity_log import ActivityLog
from app.telegram.keyboards import get_task_card_keyboard
from app.telegram.pc.helpers import _get_user_by_chat, _require_user, personal_router
from app.timeutils import local_today


@personal_router.message(F.text.in_(["📋 План дня", "План дня", "/tasks", "/today"]))
async def handle_tasks_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    today = local_today()
    today_dt_start = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=UTC)

    async with async_session_factory() as db:
        completed_stmt = select(func.count()).select_from(ActivityLog).where(
            ActivityLog.user_id == user.id,
            ActivityLog.status == "completed",
            ActivityLog.completed_at >= today_dt_start,
        )
        completed_count = (await db.execute(completed_stmt)).scalar() or 0

        active_stmt = (
            select(ActivityLog)
            .where(
                ActivityLog.user_id == user.id,
                ActivityLog.status.in_(["planned", "in_progress"]),
            )
            .order_by(ActivityLog.scheduled_at.asc().nulls_last(), ActivityLog.created_at.desc())
            .limit(5)
        )
        active_tasks = (await db.execute(active_stmt)).scalars().all()

    if not active_tasks:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🤖 Подобрать практику через AI", callback_data="ai_gen:auto")],
                [InlineKeyboardButton(text="🔄 Обновить список", callback_data="nav_tasks")],
            ]
        )
        msg = (
            "📋 *План на сегодня*\n\n"
            f"✅ Выполнено сегодня: *{completed_count}* задач\n"
            "📭 Активных задач в очереди нет. Все запланированные практики выполнены! 🎉\n\n"
            "Нажмите кнопку ниже, чтобы AI подобрал следующую активность из вашего каталога:"
        )
        await message.answer(msg, parse_mode="Markdown", reply_markup=kb)
        return

    first_task = active_tasks[0]
    total_active = len(active_tasks)

    header = (
        f"📋 *План на сегодня*\n"
        f"Выполнено: *{completed_count}* | В очереди: *{total_active}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    name = first_task.title_override or first_task.selected_entity_name or "Практика"
    params = first_task.selected_params or {}
    lines = [header, f"🎯 *Текущая задача:* **{name}**"]

    duration = params.get("duration_min")
    if duration:
        d_max = params.get("duration_max", duration)
        lines.append(f"⏱ Время: *{duration}*–*{d_max}* мин")
    if params.get("intensity"):
        lines.append(f"⚡ Интенсивность: *{params['intensity']}/5*")
    if params.get("description"):
        lines.append(f"📝 _{params['description']}_")

    if total_active > 1:
        lines.append(f"\n_Следующие в очереди ({total_active - 1}):_")
        for idx, t in enumerate(active_tasks[1:], start=2):
            t_name = t.title_override or t.selected_entity_name or "Практика"
            lines.append(f"{idx}. {t_name}")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_task_card_keyboard(first_task.id),
    )


@personal_router.callback_query(F.data == "nav_tasks")
async def cb_nav_tasks(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await handle_tasks_tab(callback.message, state)
    await callback.answer()


@personal_router.callback_query(F.data.startswith("done:"))
async def cb_task_done(callback: types.CallbackQuery):
    log_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    try:
        log_id = uuid.UUID(log_id_str)
    except ValueError:
        await callback.answer("Неверный ID задачи.", show_alert=True)
        return

    async with async_session_factory() as db:
        res = await db.execute(
            select(ActivityLog).where(ActivityLog.id == log_id, ActivityLog.user_id == user.id)
        )
        log = res.scalar_one_or_none()
        if not log:
            await callback.answer("Задача не найдена или уже завершена.", show_alert=True)
            return

        if log.status == "completed":
            await callback.answer("Эта задача уже отмечена как выполненная!", show_alert=True)
            return

        log.status = "completed"
        log.completed_at = datetime.now(UTC)
        db.add(log)
        await db.flush()

        gamification = await on_task_completed(db, user.id, log)
        await db.commit()

    task_name = log.title_override or log.selected_entity_name or "Практика"
    earned_xp = gamification.get("xp_earned", 0)
    total_xp = gamification.get("total_xp", 0)
    level = gamification.get("level", 1)
    pts = gamification.get("points_earned", 0)

    result_lines = [
        f"✅ **{task_name}** — выполнено! 🎉",
        f"⭐ +{earned_xp} XP (всего: {total_xp}, уровень {level})",
    ]
    if pts:
        result_lines.append(f"💰 +{pts} баллов")
    if gamification.get("leveled_up"):
        result_lines.append("🆙 **НОВЫЙ УРОВЕНЬ!** Поздравляем!")
    if gamification.get("new_achievements"):
        result_lines.append(f"🏆 Открыто достижений: {gamification['new_achievements']}!")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 К плану дня", callback_data="nav_tasks")],
            [InlineKeyboardButton(text="🤖 Следующая через AI", callback_data="ai_gen:auto")],
        ]
    )
    await callback.message.edit_text("\n".join(result_lines), parse_mode="Markdown", reply_markup=kb)
    await callback.answer("Отлично! Задача завершена 🎉")


@personal_router.callback_query(F.data.startswith("task_skip:"))
async def cb_task_skip(callback: types.CallbackQuery):
    log_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    try:
        log_id = uuid.UUID(log_id_str)
    except ValueError:
        await callback.answer("Неверный ID задачи.", show_alert=True)
        return

    async with async_session_factory() as db:
        res = await db.execute(
            select(ActivityLog).where(ActivityLog.id == log_id, ActivityLog.user_id == user.id)
        )
        log = res.scalar_one_or_none()
        if not log:
            await callback.answer("Задача не найдена.", show_alert=True)
            return

        log.status = "skipped"
        db.add(log)
        await db.commit()

    task_name = log.title_override or log.selected_entity_name or "Практика"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📋 К плану дня", callback_data="nav_tasks")]]
    )
    await callback.message.edit_text(
        f"⏭ Задача **{task_name}** пропущена (без штрафов и наград).",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Пропущено")


@personal_router.callback_query(F.data.startswith("int:"))
async def cb_task_interrupt_prompt(callback: types.CallbackQuery):
    log_id_str = callback.data.split(":", 1)[1]
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚠️ Да, прервать", callback_data=f"int_confirm:{log_id_str}"),
                InlineKeyboardButton(text="Отмена", callback_data="nav_tasks"),
            ]
        ]
    )
    await callback.message.edit_text(
        "⚠️ **Подтверждение прерывания**\n\n"
        "Прерывание начатой задачи начисляет штраф в соответствии с правилами геймификации.\n"
        "Вы действительно хотите прервать выполнение?",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer()


@personal_router.callback_query(F.data.startswith("int_confirm:"))
async def cb_task_interrupt_confirm(callback: types.CallbackQuery):
    log_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    try:
        log_id = uuid.UUID(log_id_str)
    except ValueError:
        await callback.answer("Неверный ID задачи.", show_alert=True)
        return

    async with async_session_factory() as db:
        res = await db.execute(
            select(ActivityLog).where(ActivityLog.id == log_id, ActivityLog.user_id == user.id)
        )
        log = res.scalar_one_or_none()
        if not log:
            await callback.answer("Задача не найдена.", show_alert=True)
            return

        log.status = "stopped"
        db.add(log)
        await db.flush()

        gamification = await on_task_interrupted(db, user.id, log)
        await db.commit()

    task_name = log.title_override or log.selected_entity_name or "Практика"
    penalty = gamification.get("penalty", {})
    penalty_msg = f"Штраф: -{penalty.get('xp_penalty', 0)} XP" if penalty else "Применён штраф"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📋 К плану дня", callback_data="nav_tasks")]]
    )
    await callback.message.edit_text(
        f"⏹ Задача **{task_name}** прервана.\n⚠️ {penalty_msg}",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Прервано со штрафом", show_alert=True)


@personal_router.callback_query(F.data.startswith("task_custom:"))
async def cb_task_custom_params(callback: types.CallbackQuery):
    log_id_str = callback.data.split(":", 1)[1]
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏱ 10 мин", callback_data=f"set_min:{log_id_str}:10"),
                InlineKeyboardButton(text="⏱ 20 мин", callback_data=f"set_min:{log_id_str}:20"),
                InlineKeyboardButton(text="⏱ 30 мин", callback_data=f"set_min:{log_id_str}:30"),
            ],
            [
                InlineKeyboardButton(text="⏱ 45 мин", callback_data=f"set_min:{log_id_str}:45"),
                InlineKeyboardButton(text="⏱ 60 мин", callback_data=f"set_min:{log_id_str}:60"),
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="nav_tasks")],
        ]
    )
    await callback.message.edit_text(
        "⚙️ **Укажите фактическое время выполнения:**\n"
        "Выберите длительность для завершения задачи с точными параметрами:",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer()


@personal_router.callback_query(F.data.startswith("set_min:"))
async def cb_task_custom_set_min(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    log_id_str = parts[1]
    mins = int(parts[2])

    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    try:
        log_id = uuid.UUID(log_id_str)
    except ValueError:
        await callback.answer("Неверный ID задачи.", show_alert=True)
        return

    async with async_session_factory() as db:
        res = await db.execute(
            select(ActivityLog).where(ActivityLog.id == log_id, ActivityLog.user_id == user.id)
        )
        log = res.scalar_one_or_none()
        if not log:
            await callback.answer("Задача не найдена.", show_alert=True)
            return

        log.status = "completed"
        log.completed_at = datetime.now(UTC)
        log.actual_parameters = {"duration_min": mins}
        db.add(log)
        await db.flush()

        gamification = await on_task_completed(db, user.id, log)
        await db.commit()

    task_name = log.title_override or log.selected_entity_name or "Практика"
    earned_xp = gamification.get("xp_earned", 0)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📋 К плану дня", callback_data="nav_tasks")]]
    )
    await callback.message.edit_text(
        f"✅ **{task_name}** завершено!\n"
        f"⏱ Зафиксированное время: *{mins}* мин\n"
        f"⭐ +{earned_xp} XP",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Сохранено и выполнено! 🎉")
