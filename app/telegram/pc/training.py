"""Personal Contour — Training & Workouts."""

from __future__ import annotations

import logging
import uuid

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database import async_session_factory
from app.models.progress import UserProgress
from app.models.training import TrainingDay
from app.services import training_service
from app.telegram.keyboards import get_training_keyboard
from app.telegram.pc.helpers import (
    _get_user_by_chat,
    _progress_bar,
    _require_user,
    personal_router,
)
from app.timeutils import local_today

logger = logging.getLogger(__name__)


@personal_router.message(F.text.in_(["🏋️ Тренировка", "Тренировка", "/training", "/workout"]))
async def handle_training_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    today = local_today()
    async with async_session_factory() as db:
        stmt = (
            select(TrainingDay)
            .where(TrainingDay.user_id == user.id, TrainingDay.scheduled_date == today)
            .order_by(TrainingDay.created_at.desc())
        )
        day = (await db.execute(stmt)).scalar_one_or_none()

    if not day:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🤖 Сгенерировать тренировку (AI)", callback_data="tr_gen_ai")],
                [InlineKeyboardButton(text="📋 К плану дня", callback_data="nav_tasks")],
            ]
        )
        await message.answer(
            "🏋️ *Тренировочный день на сегодня*\n\n"
            "На сегодня отдельная тренировка не запланирована.\n"
            "Вы можете сгенерировать адаптивную программу через ИИ или открыть конструктор на сайте.",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return

    subtasks = day.subtasks or []
    completed_sub = sum(1 for s in subtasks if s.get("is_done"))
    total_sub = len(subtasks)
    is_completed = day.status == "completed"

    lines = [
        f"🏋️ *Тренировка:* **{day.title}**",
        f"Статус: *{'✅ Завершена' if is_completed else '⏳ В процессе'}*",
        f"Прогресс: *{completed_sub}/{total_sub}* упражнений {_progress_bar(completed_sub, total_sub, 6)}\n",
    ]

    if day.focus_area:
        lines.append(f"🎯 Фокус: *{day.focus_area}*")
    if day.intensity:
        lines.append(f"⚡ Нагрузка: *{day.intensity}/5*")

    if subtasks:
        lines.append("\n*Упражнения:*")
        for idx, st in enumerate(subtasks, 1):
            icon = "✅" if st.get("is_done") else "⏳"
            desc = st.get("desc") or st.get("title") or "Упражнение"
            lines.append(f"{idx}. {icon} {desc}")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_training_keyboard(day.id, subtasks=subtasks, is_completed=is_completed),
    )


@personal_router.callback_query(F.data == "nav_training")
async def cb_nav_training(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await handle_training_tab(callback.message, state)
    await callback.answer()


@personal_router.callback_query(F.data == "tr_gen_ai")
async def cb_training_generate_ai(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    await callback.message.edit_text("🤖 ИИ составляет план тренировки на сегодня...")
    await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")

    today = local_today()
    async with async_session_factory() as db:
        try:
            plan = await training_service.generate_plan(db, user, target_date=today)
            await db.commit()
        except Exception as exc:
            logger.exception("Failed to generate training plan via AI")
            await callback.message.edit_text(f"❌ Ошибка генерации тренировки: {exc}")
            return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏋️ Открыть тренировку", callback_data="nav_training")]]
    )
    title = plan.get("title", "Тренировочный комплекс") if isinstance(plan, dict) else "Тренировка"
    await callback.message.edit_text(
        f"🎉 **{title}** успешно составлена через AI!\nОткройте программу и отмечайте подходы:",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Тренировка создана! 🏋️")


@personal_router.callback_query(F.data.startswith("tr_toggle:"))
async def cb_training_toggle_subtask(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    day_id = uuid.UUID(parts[1])
    idx = int(parts[2])

    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    async with async_session_factory() as db:
        day = await db.get(TrainingDay, day_id)
        if not day or day.user_id != user.id:
            await callback.answer("Тренировка не найдена.", show_alert=True)
            return

        subtasks = list(day.subtasks or [])
        if 0 <= idx < len(subtasks):
            subtasks[idx]["is_done"] = not subtasks[idx].get("is_done", False)
            day.subtasks = subtasks
            db.add(day)
            await db.commit()

    await callback.answer("Статус обновлён!")
    await callback.message.delete()
    await handle_training_tab(callback.message, FSMContext)  # type: ignore


@personal_router.callback_query(F.data.startswith("tr_complete:"))
async def cb_training_complete(callback: types.CallbackQuery):
    day_id = uuid.UUID(callback.data.split(":", 1)[1])
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    async with async_session_factory() as db:
        day = await db.get(TrainingDay, day_id)
        if not day or day.user_id != user.id:
            await callback.answer("Тренировка не найдена.", show_alert=True)
            return

        day.status = "completed"
        db.add(day)

        progress = (await db.execute(select(UserProgress).where(UserProgress.user_id == user.id))).scalar_one_or_none()
        xp_gain = 50
        if progress:
            progress.xp += xp_gain
            db.add(progress)

        await db.commit()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏋️ К тренировкам", callback_data="nav_training")]]
    )
    await callback.message.edit_text(
        f"🏆 Тренировка **{day.title}** успешно завершена!\n"
        f"⭐ +{xp_gain} XP за физическую активность!",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Тренировка завершена! 💪")


@personal_router.callback_query(F.data.startswith("tr_adapt:"))
async def cb_training_adapt(callback: types.CallbackQuery):
    day_id = uuid.UUID(callback.data.split(":", 1)[1])
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    await callback.message.edit_text("🤖 ИИ адаптирует нагрузку тренировки...")
    await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")

    async with async_session_factory() as db:
        try:
            analysis = await training_service.analyze_day(db, user, day_id)
            await db.commit()
        except Exception as e:
            await callback.message.edit_text(f"❌ Ошибка адаптации: {e}")
            return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏋️ Вернуться к тренировке", callback_data="nav_training")]]
    )
    rec = analysis.get("recommendation", "Нагрузка скорректирована с учётом вашего текущего состояния.")
    await callback.message.edit_text(
        f"🤖 **Рекомендация ИИ-тренера:**\n\n_{rec}_",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Адаптировано")
