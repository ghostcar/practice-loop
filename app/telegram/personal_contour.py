"""Telegram Bot Router for Personal Contour (ADR-193).

Implements convenient mobile interactions for:
- 📋 Today's Tasks & Execution (1-click completion, skipping, interruptions)
- 💊 Medication intake by time slots (batch intake, individual intake, kit overview)
- 🤖 AI activity generation (strict LLM-only creation as per owner requirements)
- 🏋️ Workout tracking (subtask checklist, workout completion, AI adaptation)
- ❤️ Health check-in (mood, energy, cycle, weight measurements)
- 🏆 Progress & Gamification (XP, streaks, points, penalty redemptions, quests)
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import UTC, datetime

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.gamification.handler import on_task_completed, on_task_interrupted
from app.gamification.medication import on_medication_taken
from app.llm.pipeline import generate_task, get_active_llm_config
from app.llm.repair import JsonRepairError
from app.models.activity_log import ActivityLog
from app.models.health import HealthState
from app.models.life import BodyMeasurement
from app.models.medication import MedKit, MedSchedule
from app.models.points import PenaltyRedemption, PointsTransaction
from app.models.progress import UserProgress
from app.models.quest import UserQuest
from app.models.training import TrainingDay
from app.models.user import User
from app.prefs import prefs_from_dict
from app.services import med_service as med_svc
from app.services import training_service
from app.services import wear_reactive_service as wear_svc
from app.services.health_service import get_cycle_context
from app.telegram.keyboards import (
    get_ai_generator_keyboard,
    get_health_keyboard,
    get_main_reply_keyboard,
    get_med_slot_keyboard,
    get_stats_keyboard,
    get_task_card_keyboard,
    get_training_keyboard,
    get_wear_card_keyboard,
    get_wear_comfort_keyboard,
    get_wear_reasons_keyboard,
)
from app.timeutils import as_utc, local_today

logger = logging.getLogger(__name__)

personal_router = Router(name="personal_contour")


class PersonalStates(StatesGroup):
    waiting_for_weight = State()
    waiting_for_custom_duration = State()
    waiting_for_wear_start_tag = State()
    waiting_for_wear_agent_reason = State()
    waiting_for_wear_relock_tag = State()
    waiting_for_wear_inspection_tag = State()
    waiting_for_wear_orgasm_notes = State()


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _get_user_by_chat(chat_id: int) -> User | None:
    async with async_session_factory() as db:
        res = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
        return res.scalar_one_or_none()


async def _try_link_by_code(message: types.Message, raw_code: str, db: AsyncSession | None = None) -> bool:
    code = raw_code.strip()
    if code.lower().startswith("link_"):
        code = code[5:]
    if not code:
        return False

    clean_code = code.upper()

    async def _do_linking(session: AsyncSession) -> bool:
        from app.models.ds_suite import ManagedSubmissive

        # 1. Check User by telegram_link_code
        res = await session.execute(select(User).where(User.telegram_link_code == clean_code))
        user = res.scalar_one_or_none()
        if user:
            if user.telegram_link_code_expires and as_utc(user.telegram_link_code_expires) < datetime.now(UTC):
                await message.answer("⏰ Срок действия кода привязки истёк. Сгенерируйте новый код в профиле на сайте.")
                return True

            user.telegram_chat_id = message.chat.id
            user.telegram_link_code = None
            user.telegram_link_code_expires = None
            session.add(user)
            await session.commit()

            name = user.display_name or user.email.split("@")[0]
            await message.answer(
                f"🎉 **Аккаунт успешно привязан!**\n\n"
                f"Добро пожаловать, **{name}**!\n"
                "Персональный контур и главное меню активированы.",
                parse_mode="Markdown",
                reply_markup=get_main_reply_keyboard(),
            )
            return True

        # 2. Check ManagedSubmissive (D/s suite)
        sub_stmt = select(ManagedSubmissive).where(ManagedSubmissive.telegram_link_code == clean_code)
        sub_profile = (await session.execute(sub_stmt)).scalar_one_or_none()
        if sub_profile:
            exp = sub_profile.telegram_link_code_expires
            if exp and as_utc(exp) < datetime.now(UTC):
                await message.answer("⏰ Срок действия кода истёк. Запросите новый код у Ключника.")
                return True

            sub_profile.telegram_chat_id = str(message.chat.id)
            sub_profile.telegram_link_code = None
            sub_profile.telegram_link_code_expires = None
            session.add(sub_profile)
            await session.commit()

            await message.answer(
                f"👑 **D/s профиль привязан!** Добро пожаловать, **{sub_profile.name}**!\n\n"
                "Уведомления и задачи от Ключника подключены.",
                parse_mode="Markdown",
            )
            return True

        return False

    if db is not None:
        return await _do_linking(db)

    async with async_session_factory() as session:
        return await _do_linking(session)


async def _require_user(message: types.Message) -> User | None:
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await message.answer(
            "👋 **Ваш Telegram ещё не привязан к аккаунту PracticeLoop.**\n\n"
            "Выберите удобный способ привязки:\n"
            "1. **В 1 клик:** нажмите кнопку «Подключить Telegram» в вашем профиле на сайте.\n"
            "2. **Код из бота:** отправьте команду `/connect` — бот выдаст 6-значный OTP для ввода на сайте.\n"
            "3. **Код с сайта:** отправьте сюда команду `/link ВАШ_КОД`.",
            parse_mode="Markdown",
        )
        return None
    return user


def _progress_bar(current: int, total: int, length: int = 8) -> str:
    if total <= 0:
        return "░" * length
    filled = min(length, int((current / total) * length))
    return "█" * filled + "░" * (length - filled)


# ── Navigation & Root Menu ───────────────────────────────────────────────────


async def _send_welcome_menu(message: types.Message, user: User) -> None:
    name = user.display_name or user.email.split("@")[0]
    text = (
        f"👋 Рады видеть вас, **{name}**!\n\n"
        "📱 **Персональный контур PracticeLoop активен.**\n"
        "Используйте постоянное меню снизу для быстрого доступа:\n\n"
        "• 📋 **План дня** — задачи на сегодня и отметка выполнения в 1 клик\n"
        "• 💊 **Лекарства** — приём по слотам и сканер пачек\n"
        "• 🤖 **AI-генератор** — умный подбор практик через ИИ\n"
        "• 🏋️ **Тренировка** — программа на день и упражнения\n"
        "• ❤️ **Чек-ин / Замеры** — самочувствие, вес и цикл\n"
        "• 🏆 **Прогресс** — опыт, серия дней и отработка штрафов\n\n"
        "💬 _Вы также можете просто написать мне любой вопрос или пожелание к практике текстом или голосом._"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_reply_keyboard())


@personal_router.message(Command("start"))
async def cmd_start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        linked = await _try_link_by_code(message, parts[1])
        if linked:
            return

    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await _require_user(message)
        return

    await _send_welcome_menu(message, user)


@personal_router.message(Command("menu"))
async def cmd_personal_menu(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return
    await _send_welcome_menu(message, user)


@personal_router.message(Command("link"))
async def cmd_link_handler(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Формат: `/link ВАШ_КОД`\n"
            "Код привязки можно скопировать в вашем профиле на портале.",
            parse_mode="Markdown",
        )
        return
    linked = await _try_link_by_code(message, parts[1])
    if not linked:
        await message.answer(
            "❌ Неверный или устаревший код привязки.\n"
            "Сгенерируйте свежий код в веб-профиле или отправьте команду `/connect` для получения OTP-кода."
        )


@personal_router.message(Command("connect"))
@personal_router.message(Command("otp"))
async def cmd_connect_otp_handler(message: types.Message):
    user = await _get_user_by_chat(message.chat.id)
    if user is not None:
        await message.answer(
            f"ℹ️ Ваш Telegram уже привязан к аккаунту **{user.email}**.\n"
            "Чтобы отвязать его, отправьте команду `/unlink`.",
            parse_mode="Markdown",
        )
        return

    from app.services.telegram_link_service import create_bot_connect_code

    otp = create_bot_connect_code(
        chat_id=message.chat.id,
        username=message.from_user.username if message.from_user else None,
        first_name=message.from_user.first_name if message.from_user else None,
        ttl_minutes=10,
    )
    text = (
        "🔑 **Ваш одноразовый код (OTP) для портала:**\n\n"
        f"`{otp}`\n"
        "_(нажмите на код выше, чтобы скопировать)_\n\n"
        "⏱ Код действует 10 минут.\n"
        "Откройте на сайте **Профиль → Telegram**, введите эти 6 цифр в поле ввода и нажмите **«Привязать»**."
    )
    await message.answer(text, parse_mode="Markdown")


@personal_router.message(Command("unlink"))
async def cmd_unlink_handler(message: types.Message):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await message.answer("Ваш Telegram-аккаунт не привязан ни к одному профилю.")
        return

    from app.services.telegram_link_service import unlink_user_telegram

    async with async_session_factory() as db:
        await unlink_user_telegram(db, user)
        await db.commit()

    await message.answer(
        "ℹ️ Ваш Telegram-аккаунт успешно отвязан от портала PracticeLoop.",
        reply_markup=types.ReplyKeyboardRemove(),
    )


# ── 1. 📋 План дня (Today's Tasks) ──────────────────────────────────────────


@personal_router.message(F.text.in_(["📋 План дня", "План дня", "/tasks", "/today"]))
async def handle_tasks_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    today = local_today()
    today_dt_start = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=UTC)

    async with async_session_factory() as db:
        # Completed today
        completed_stmt = select(func.count()).select_from(ActivityLog).where(
            ActivityLog.user_id == user.id,
            ActivityLog.status == "completed",
            ActivityLog.completed_at >= today_dt_start,
        )
        completed_count = (await db.execute(completed_stmt)).scalar() or 0

        # Planned / in-progress tasks
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


# ── 2. 💊 Лекарства (Medications & Slot Intakes) ─────────────────────────────


@personal_router.message(F.text.in_(["💊 Лекарства", "Лекарства", "/med", "/meds"]))
async def handle_medications_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    async with async_session_factory() as db:
        summary = await med_svc.schedule_summary(db, user_id=user.id)

    slots = summary.get("slots", [])
    pending_slots = [s for s in slots if s.get("pending")]

    lines = ["💊 *Приём лекарств на сегодня*"]
    total_doses = sum(len(s.get("meds", [])) for s in slots)
    taken_doses = sum(sum(1 for m in s.get("meds", []) if m.get("taken")) for s in slots)
    if total_doses > 0:
        lines.append(f"Прогресс: *{taken_doses}/{total_doses}* приёмов\n")

    if not pending_slots:
        lines.append("🎉 *Все лекарства на сегодня приняты! Отличная дисциплина.*")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📸 Сканировать пачку", callback_data="med_scan_guide")],
                [InlineKeyboardButton(text="📦 Мои аптечки", callback_data="med_kits_view")],
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="nav_meds")],
            ]
        )
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
        return

    # Render first pending slot with one-click batch intake
    first_slot = pending_slots[0]
    slot_time = first_slot.get("time", "Сегодня")
    slot_key = slot_time
    lines.append(f"⏰ *Ближайший слот:* **{slot_time}**")

    items = first_slot.get("meds", [])
    for it in items:
        status_icon = "✅" if it.get("taken") else "⏳"
        food_note = f" ({it['food_relation']})" if it.get("food_relation") else ""
        lines.append(f"• {status_icon} *{it['medication_name']}* — {it.get('dose', '1 доза')}{food_note}")

    if len(pending_slots) > 1:
        lines.append(f"\n_Ещё запланировано слотов: {len(pending_slots) - 1}_")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_med_slot_keyboard(slot_key, slot_time, individual_items=items),
    )


@personal_router.callback_query(F.data == "nav_meds")
async def cb_nav_meds(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await handle_medications_tab(callback.message, state)
    await callback.answer()


@personal_router.callback_query(F.data.startswith("med_slot_take:"))
async def cb_med_slot_take(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    _slot_key = parts[1]
    slot_time = parts[2]

    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    async with async_session_factory() as db:
        summary = await med_svc.schedule_summary(db, user_id=user.id)
        matching_slot = next((s for s in summary.get("slots", []) if s.get("time") == slot_time), None)
        if not matching_slot:
            await callback.answer("Слот не найден или уже отмечен.", show_alert=True)
            return

        schedule_ids = [
            uuid.UUID(it["schedule_id"])
            for it in matching_slot.get("meds", [])
            if not it.get("taken") and it.get("schedule_id")
        ]

        if not schedule_ids:
            await callback.answer("Все препараты этого слота уже приняты!", show_alert=True)
            return

        await med_svc.record_batch_intake(db, user_id=user.id, schedule_ids=schedule_ids, slot_time=slot_time)
        res_xp = await on_medication_taken(db, user.id, f"Слот {slot_time}", on_time=True)
        await db.commit()

    xp = res_xp.get("xp_earned", 15)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💊 К расписанию лекарств", callback_data="nav_meds")]]
    )
    await callback.message.edit_text(
        f"✅ Приём лекарств за **{slot_time}** выполнен!\n"
        f"Остатки в аптечках пересчитаны.\n"
        f"⭐ +{xp} XP за дисциплину приёма! 💊",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Принято! 💊")


@personal_router.callback_query(F.data.startswith("med_take:"))
async def cb_med_take_one(callback: types.CallbackQuery):
    sched_id_str = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    try:
        sched_id = uuid.UUID(sched_id_str)
    except ValueError:
        await callback.answer("Неверный ID.", show_alert=True)
        return

    async with async_session_factory() as db:
        await med_svc.record_batch_intake(db, user_id=user.id, schedule_ids=[sched_id], slot_time="now")
        sched = (
            await db.execute(select(MedSchedule).where(MedSchedule.id == sched_id))
        ).scalar_one_or_none()
        name = sched.medication.name if sched and sched.medication else "Препарат"
        res_xp = await on_medication_taken(db, user.id, name, on_time=True)
        await db.commit()

    xp = res_xp.get("xp_earned", 10)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💊 К расписанию", callback_data="nav_meds")]]
    )
    await callback.message.edit_text(
        f"✅ Препарат *{name}* принят.\n⭐ +{xp} XP",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer("Принято! 💊")


@personal_router.callback_query(F.data == "med_kits_view")
async def cb_med_kits_view(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        stmt = select(MedKit).where(MedKit.user_id == user.id).order_by(MedKit.name)
        kits = (await db.execute(stmt)).scalars().all()
        summary = await med_svc.schedule_summary(db, user.id)

    lines = ["📦 *Ваши аптечки и запасы*\n"]
    if not kits:
        lines.append("У вас пока нет созданных аптечек. Создайте их в веб-интерфейсе на сайте.")
    else:
        for k in kits:
            loc = f" 📍 {k.location_id}" if k.location_id else ""
            lines.append(f"• **{k.name}**{loc}")

    low = summary.get("low_stock", [])
    if low:
        lines.append("\n⚠️ *Заканчивающиеся препараты:*")
        for item in low[:4]:
            lines.append(f"• {item['medication_name']} — осталось {item['quantity']:g}")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 Сканировать DataMatrix", callback_data="med_scan_guide")],
            [InlineKeyboardButton(text="💊 Назад к лекарствам", callback_data="nav_meds")],
        ]
    )
    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@personal_router.callback_query(F.data == "med_scan_guide")
async def cb_med_scan_guide(callback: types.CallbackQuery):
    await callback.message.answer(
        "📸 *Сканирование маркировки (Честный Знак)*\n\n"
        "Просто отправьте фотографию квадратного DataMatrix-кода с упаковки препарата в этот чат.\n"
        "Бот автоматически считает серию, срок годности, GTIN и предложит добавить пачку в аптечку!",
        parse_mode="Markdown",
    )
    await callback.answer()


# ── 3. 🤖 AI-генератор активностей ──────────────────────────────────────────


@personal_router.message(F.text.in_(["🤖 AI-генератор", "AI-генератор", "/next", "/generate"]))
async def handle_ai_generator_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    text = (
        "🤖 **AI-генератор персональных практик**\n\n"
        "Искусственный интеллект подбирает активности исключительно из вашего "
        "допустимого каталога (opt-in) на основе недавней истории и баланса нагрузок.\n\n"
        "Выберите готовый пресет или просто напишите мне сообщение с пожеланием "
        "(например: _«Хочу растяжку для спины на 15 минут»_ или _«Подбери расслабляющую практику на вечер»_):"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_ai_generator_keyboard())


@personal_router.callback_query(F.data.startswith("ai_gen:"))
async def cb_ai_generate_task(callback: types.CallbackQuery):
    mode = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    await callback.message.edit_text("🤖 ИИ анализирует ваш профиль и подбирает активность...")
    await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")

    preset_prompts = {
        "quick": "Подбери быструю и эффективную активность длительностью от 10 до 15 минут.",
        "relax": (
            "Подбери мягкую расслабляющую практику низкой интенсивности (1-2 из 5), "
            "направленную на покой и снятие напряжения."
        ),
        "intense": "Подбери активную, стимулирующую практику высокой интенсивности (4-5 из 5).",
        "auto": None,
    }
    user_prompt = preset_prompts.get(mode)

    async with async_session_factory() as db:
        config = await get_active_llm_config(db, user.id)
        if config is None:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="📋 К плану дня", callback_data="nav_tasks")]]
            )
            await callback.message.edit_text(
                "❌ В вашем профиле не настроен активный провайдер LLM.\n"
                "Подключите ключ (Omniroute / OpenRouter / Groq) в настройках на сайте "
                "или выберите портального провайдера.",
                reply_markup=kb,
            )
            return

        try:
            log = await generate_task(
                db=db,
                user_id=user.id,
                llm_config=config,
                session_id=None,
                user_prompt=user_prompt,
                locale=user.locale or "ru",
                llm_mode=prefs_from_dict(user.prefs).llm_mode,
            )
            await db.commit()
        except JsonRepairError:
            await callback.message.edit_text("❌ Ответ ИИ не удалось разобрать. Попробуйте ещё раз.")
            return
        except ValueError as e:
            await callback.message.edit_text(f"❌ {e}")
            return
        except Exception:
            logger.exception("AI generation failed in bot")
            await callback.message.edit_text("❌ Запрос к модели завершился ошибкой. Проверьте настройки LLM.")
            return

    name = log.title_override or log.selected_entity_name or "Практика"
    params = log.selected_params or {}
    cleaned = log.cleaned_response or {}
    reasoning = cleaned.get("reasoning") or params.get("reasoning")

    lines = [
        "🎲 **Новая активность подобрана через AI:**",
        f"🎯 **{name}**",
    ]
    if params.get("duration_min"):
        d_min = params["duration_min"]
        d_max = params.get("duration_max", d_min)
        lines.append(f"⏱ Время: *{d_min}*–*{d_max}* мин")
    if params.get("intensity"):
        lines.append(f"⚡ Интенсивность: *{params['intensity']}/5*")
    if params.get("description"):
        lines.append(f"📝 _{params['description']}_")
    if reasoning:
        lines.append(f"\n💡 *Почему выбрана:* _{reasoning}_")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_task_card_keyboard(log.id),
    )
    await callback.answer("Готово! Активность создана.")


# ── 4. 🏋️ Тренировка (Workouts & Training) ───────────────────────────────────


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
    # Refresh training view
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

        # Gamification reward for completing a workout
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


# ── 5. ❤️ Чек-ин & Замеры (Health, Cycle, Body Measurements) ────────────────


@personal_router.message(F.text.in_(["❤️ Чек-ин / Замеры", "Чек-ин / Замеры", "/health", "/checkin", "/cycle"]))
async def handle_health_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    today = local_today()
    async with async_session_factory() as db:
        state_row = (
            await db.execute(
                select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == today)
            )
        ).scalar_one_or_none()
        cycle = await get_cycle_context(db, user.id)
        latest_meas = (
            await db.execute(
                select(BodyMeasurement)
                .where(BodyMeasurement.user_id == user.id)
                .order_by(BodyMeasurement.measured_date.desc(), BodyMeasurement.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    lines = ["❤️ *Дневной чек-ин и показатели тела*"]
    mood_val = state_row.mood if state_row else None
    energy_val = state_row.energy if state_row else None

    lines.append(f"⭐ Настроение: *{'⭐' * mood_val if mood_val else 'не отмечено'}*")
    lines.append(f"⚡ Энергия: *{'⚡' * energy_val if energy_val else 'не отмечено'}*")

    if latest_meas and latest_meas.weight:
        lines.append(f"⚖️ Текущий вес: *{latest_meas.weight:g}* кг (от {latest_meas.measured_date.strftime('%d.%m')})")
    else:
        lines.append("⚖️ Вес: _ещё не записан_")

    if cycle.get("phase"):
        lines.append(f"🌸 Фаза цикла: *{cycle['phase']}* (день {cycle['day_of_cycle']})")

    lines.append("\n_Отметьте самочувствие шкалой ниже или запишите вес:_")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_health_keyboard(mood=mood_val, energy=energy_val),
    )


@personal_router.callback_query(F.data.startswith("health_mood:"))
async def cb_health_mood(callback: types.CallbackQuery):
    val = int(callback.data.split(":", 1)[1])
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    today = local_today()
    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == today)
            )
        ).scalar_one_or_none()
        if not row:
            row = HealthState(user_id=user.id, event_date=today)
            db.add(row)
        row.mood = val
        await db.commit()

    await callback.answer(f"Настроение сохранено: {val}/5 ⭐")


@personal_router.callback_query(F.data.startswith("health_energy:"))
async def cb_health_energy(callback: types.CallbackQuery):
    val = int(callback.data.split(":", 1)[1])
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    today = local_today()
    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == today)
            )
        ).scalar_one_or_none()
        if not row:
            row = HealthState(user_id=user.id, event_date=today)
            db.add(row)
        row.energy = val
        await db.commit()

    await callback.answer(f"Энергия сохранена: {val}/5 ⚡")


@personal_router.callback_query(F.data == "health_weight_prompt")
async def cb_health_weight_prompt(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PersonalStates.waiting_for_weight)
    await callback.message.answer(
        "⚖️ **Запись веса**\n\nОтправьте ваш текущий вес в килограммах (например: `72.5`):"
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_weight)
async def process_weight_input(message: types.Message, state: FSMContext):
    user = await _require_user(message)
    if user is None:
        await state.clear()
        return

    raw = (message.text or "").strip().replace(",", ".")
    try:
        weight_val = float(raw)
        if weight_val < 20 or weight_val > 350:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите корректное число для веса от 20 до 350 (например: `72.5`).")
        return

    today = local_today()
    async with async_session_factory() as db:
        meas = (
            await db.execute(
                select(BodyMeasurement).where(
                    BodyMeasurement.user_id == user.id,
                    BodyMeasurement.measured_date == today,
                    BodyMeasurement.time_of_day == "morning",
                )
            )
        ).scalar_one_or_none()

        if not meas:
            meas = BodyMeasurement(
                user_id=user.id,
                measured_date=today,
                time_of_day="morning",
                weight=weight_val,
            )
            db.add(meas)
        else:
            meas.weight = weight_val

        await db.commit()

    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❤️ К дневнику здоровья", callback_data="nav_health")]]
    )
    await message.answer(
        f"✅ Вес *{weight_val:g}* кг успешно записан на {today.strftime('%d.%m.%Y')}! ⚖️",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@personal_router.callback_query(F.data == "nav_health")
async def cb_nav_health(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await handle_health_tab(callback.message, state)
    await callback.answer()


@personal_router.callback_query(F.data == "health_cycle_view")
async def cb_health_cycle_view(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        cycle = await get_cycle_context(db, user.id)

    if not cycle.get("phase"):
        await callback.answer("Данные цикла не настроены на сайте.", show_alert=True)
        return

    lines = [
        "🌸 *Женский цикл*",
        f"Фаза: *{cycle.get('phase', '—')}*",
        f"День цикла: *{cycle.get('day_of_cycle', '—')}*",
    ]
    if cycle.get("next_period"):
        lines.append(f"Следующий период (расчёт): *{cycle['next_period']}*")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❤️ Назад", callback_data="nav_health")]]
    )
    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@personal_router.callback_query(F.data == "health_care_view")
async def cb_health_care_view(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❤️ Назад", callback_data="nav_health")]]
    )
    await callback.message.edit_text(
        "🧴 *Уход и процедуры*\n\n"
        "Для просмотра текущих курсов ухода и протоколов используйте команду `/care` "
        "или перейдите в веб-интерфейс раздела Care.",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await callback.answer()


# ── 6. 🏆 Прогресс & Статус (Gamification & Redemptions) ────────────────────


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

        # Pending penalties
        pen_stmt = select(PenaltyRedemption).where(
            PenaltyRedemption.user_id == user.id,
            PenaltyRedemption.status == "pending",
        )
        penalties = (await db.execute(pen_stmt)).scalars().all()

        # Active quests
        quests_stmt = select(UserQuest).where(
            UserQuest.user_id == user.id,
            UserQuest.status == "active",
        )
        quests = (await db.execute(quests_stmt)).scalars().all()

    if not progress:
        await message.answer("📊 У вас пока нет статистики. Выполните вашу первую практику!")
        return

    has_penalties = len(penalties) > 0
    lines = [
        "🏆 *Ваш профиль и достижения*",
        f"⭐ Уровень: *{progress.level}* ({progress.xp} XP)",
        f"🔥 Серия дней подряд: *{progress.current_streak}* (рекорд: {progress.longest_streak})",
        f"💰 Баланс баллов: *{progress.points_balance}*",
        f"✅ Всего завершено практик: *{progress.total_completed}*",
        f"⏹ Прервано: *{progress.total_interrupted}*",
    ]

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

        # Credit points back
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


# ── 7. 🔒 Пояс верности (Chastity & Open-Ended Wear, ADR-195) ─────────────────


def _render_wear_card(status: dict, is_agent_mode: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    """Renders the real-time wear status card with exact second timer and actions."""
    is_active = status.get("is_active", False)
    is_locked = status.get("is_locked", False)
    lines = ["🔒 **Пояс верности: Свободный режим**\n"]

    if not is_active:
        lines.append("⚪️ **Текущее состояние: НЕ НАДЕТ (Свободен)**")
        lines.append("Активная сессия ношения пояса отсутствует.")
        lines.append("\n_Вы можете запереть пояс, зафиксировав пломбу, чтобы начать период ношения._")
    elif is_locked:
        lines.append("🟢 **Текущее состояние: ЗАПЕРТ**")
        lines.append(f"⏱ **{status['time_text']}**")
    else:
        lines.append("🔴 **Текущее состояние: СНЯТ**")
        lines.append(f"⏱ **{status['time_text']}**")

    if is_active and not is_locked and status.get("deadline_text"):
        lines.append(f"\n{status['deadline_text']}")

    pending = status.get("pending_open")
    if is_active and not is_locked and pending:
        reason_label = pending.definition.title if pending.definition else pending.event_code
        lines.append(f"\n📋 **Причина снятия:** {reason_label}")
        if pending.user_comment:
            lines.append(f"💬 _{pending.user_comment}_")
        if pending.llm_analysis:
            lines.append(f"🤖 _{pending.llm_analysis}_")

    if is_active:
        lines.append("")
        tag = status.get("current_tag")
        lines.append(f"🏷 **Пломба / Бирка:** `#{tag}`" if tag else "🏷 **Пломба / Бирка:** _нет_")

        comfort = status.get("last_comfort")
        lines.append(f"⭐ **Комфорт:** {comfort}/5" if comfort else "⭐ **Комфорт:** _не оценён_")

    slots = status.get("upcoming_slots")
    if slots:
        lines.append("\n📅 **События базового таймера на сегодня:**")
        for s in slots:
            open_t = s["planned_open_at"].strftime("%H:%M")
            close_t = s["planned_close_at"].strftime("%H:%M") if s.get("planned_close_at") else "..."
            lines.append(f"• {open_t} – {close_t} ({s['state']})")

    keyboard = get_wear_card_keyboard(
        is_active=is_active,
        is_locked=is_locked,
        is_agent_mode=is_agent_mode,
    )
    return "\n".join(lines), keyboard


@personal_router.message(F.text.in_(["🔒 Пояс", "Пояс", "/wear", "/chastity", "/lock"]))
async def msg_wear_card(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await message.answer(
            "🔒 Для управления поясом привяжите аккаунт через /link `КОД`",
            parse_mode="Markdown",
        )
        return

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)

    async with async_session_factory() as db:
        status = await wear_svc.get_wear_status(db, user.id)

    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "wear_refresh")
async def cb_wear_refresh(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)

    async with async_session_factory() as db:
        status = await wear_svc.get_wear_status(db, user.id)

    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer("⏱ Таймер обновлён")


@personal_router.callback_query(F.data == "wear_toggle_agent")
async def cb_wear_toggle_agent(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cur_agent = data.get("wear_agent_mode", False)
    new_agent = not cur_agent
    await state.update_data(wear_agent_mode=new_agent)

    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        status = await wear_svc.get_wear_status(db, user.id)

    text, kb = _render_wear_card(status, is_agent_mode=new_agent)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    status_label = "включен (свободный ввод)" if new_agent else "выключен (кнопки выбора)"
    await callback.answer(f"🤖 Агентский режим {status_label}")


@personal_router.callback_query(F.data == "wear_start_init")
async def cb_wear_start_init(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PersonalStates.waiting_for_wear_start_tag)
    await callback.message.answer(
        "🔒 **Начало ношения пояса верности**\n\n"
        "Введите номер пломбы / бирки (или отправьте `-` если закрываете без номерной бирки):\n\n"
        "_Для отмены отправьте /cancel_",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_wear_start_tag)
async def msg_wear_start_tag(message: types.Message, state: FSMContext):
    if message.text and message.text.strip().lower() in ("/cancel", "отмена"):
        await state.set_state(None)
        await message.answer("Начало ношения отменено.")
        return

    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    raw = (message.text or "").strip()
    tag_number = None if raw in ("-", "—", "") else raw

    async with async_session_factory() as db:
        session, initial_log = await wear_svc.start_open_ended_session(
            db,
            user.id,
            tag_number=tag_number,
        )
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)

    lines = ["🔒 **Пояс надет и заперт!**", "Период ношения начался, таймер запущен."]
    if tag_number:
        lines.append(f"🏷 Зафиксирована пломба: `#{tag_number}`")

    await message.answer("\n".join(lines), parse_mode="Markdown")

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "wear_finish_init")
async def cb_wear_finish_init(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    async with async_session_factory() as db:
        await wear_svc.finish_open_ended_session(db, user.id)
        status = await wear_svc.get_wear_status(db, user.id)

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)

    await callback.message.answer(
        "⏹ **Период ношения пояса завершён.** Сессия закрыта.",
        parse_mode="Markdown",
    )
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@personal_router.callback_query(F.data == "wear_unlock_init")
async def cb_wear_unlock_init(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)

    if is_agent_mode:
        await state.set_state(PersonalStates.waiting_for_wear_agent_reason)
        await callback.message.answer(
            "🤖 **Ключник слушает вас.**\n\n"
            "Опишите причину снятия пояса в свободной форме "
            "(например: _«Нужно быстро принять душ после пробежки»_ или _«Трёт и очень сильно болит»_):\n\n"
            "_Для отмены отправьте /cancel_",
            parse_mode="Markdown",
        )
        await callback.answer()
    else:
        await callback.message.edit_text(
            "🔓 **Выберите причину снятия пояса:**\n\n"
            "⏱ _Для каждой причины действует свой лимит времени. "
            "Опоздание с возвратом пояса даже на 1 секунду повлечет штраф!_",
            parse_mode="Markdown",
            reply_markup=get_wear_reasons_keyboard(),
        )
        await callback.answer()


@personal_router.callback_query(F.data.startswith("wear_reason:"))
async def cb_wear_reason_selected(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    reason_code = callback.data.split(":", 1)[1]

    async with async_session_factory() as db:
        log_entry, reactions = await wear_svc.record_unlock_event(db, user.id, reason_code)
        status = await wear_svc.get_wear_status(db, user.id)

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)

    ack_text = f"🔓 **Пояс снят.** Зафиксировано событие: `{reason_code}`."
    if reactions.get("sexual_journal_id"):
        ack_text += "\n❤️ Создана черновая запись в Сексуальном журнале."
    if reactions.get("penalty_applied"):
        ack_text += f"\n⚠️ Применен штраф: {reactions['penalty_applied']} баллов."

    await callback.message.answer(ack_text, parse_mode="Markdown")
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_wear_agent_reason)
async def msg_wear_agent_reason(message: types.Message, state: FSMContext):
    if message.text and message.text.strip().lower() in ("/cancel", "отмена"):
        await state.set_state(None)
        await message.answer("Снятие пояса отменено.")
        return

    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    user_text = message.text or ""
    await message.answer("🤖 _Анализирую запрос с Ключником..._", parse_mode="Markdown")

    from app.llm.pipeline.keyholder import classify_wear_unlock_reason

    async with async_session_factory() as db:
        llm_config = await get_active_llm_config(db, user.id)
        classified = await classify_wear_unlock_reason(user_text, llm_config, locale="ru")

        event_code = classified.get("event_code", "hygiene_quick")
        duration_mins = classified.get("duration_minutes", 10)
        keyholder_msg = classified.get("keyholder_message", "Запрос одобрен Ключником.")

        log_entry, reactions = await wear_svc.record_unlock_event(
            db,
            user.id,
            event_code=event_code,
            duration_minutes=duration_mins,
            user_comment=user_text,
            llm_analysis=keyholder_msg,
        )
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)

    resp_lines = [
        "🤖 **Вердикт Ключника:**\n",
        f"_{keyholder_msg}_\n",
        f"⏱ Установлен таймер: **{duration_mins} мин.**",
        "⚠️ _Помните: опоздание с возвратом пояса хотя бы на 1 секунду повлечет штраф!_",
    ]
    if reactions.get("sexual_journal_id"):
        resp_lines.append("❤️ Запись о близости добавлена в Сексуальный журнал.")

    await message.answer("\n".join(resp_lines), parse_mode="Markdown")

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", True)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "wear_relock_init")
async def cb_wear_relock_init(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PersonalStates.waiting_for_wear_relock_tag)
    await callback.message.answer(
        "🔒 **Закрытие пояса**\n\n"
        "Введите номер новой пломбы / бирки (или отправьте `-` если закрываете без номерной бирки):",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_wear_relock_tag)
async def msg_wear_relock_tag(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    raw = (message.text or "").strip()
    tag_number = None if raw in ("-", "—", "") else raw

    async with async_session_factory() as db:
        relock_log, reactions = await wear_svc.record_relock_event(
            db,
            user.id,
            tag_number=tag_number,
        )
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)

    lines = ["🔒 **Пояс успешно заперт!**"]
    if tag_number:
        lines.append(f"🏷 Зафиксирована пломба: `#{tag_number}`")

    if reactions.get("delay_penalty"):
        dp = reactions["delay_penalty"]
        lines.append(
            f"\n⚠️ **ВНИМАНИЕ: Зафиксировано опоздание на {dp['formatted_overdue']}!**\n"
            f"Начислен штраф: **{dp['amount']} баллов**."
        )
    else:
        lines.append("✅ Возврат выполнен вовремя без опоздания.")

    await message.answer("\n".join(lines), parse_mode="Markdown")

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "wear_inspect_init")
async def cb_wear_inspect_init(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PersonalStates.waiting_for_wear_inspection_tag)
    await callback.message.answer(
        "🔍 **Проверка пломбы / бирки (без снятия)**\n\n"
        "Пояс остаётся запертым. Введите фактический номер пломбы для подтверждения целостности:",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_wear_inspection_tag)
async def msg_wear_inspection_tag(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    tag_number = (message.text or "").strip()
    if not tag_number:
        tag_number = "verified"

    async with async_session_factory() as db:
        await wear_svc.record_seal_inspection(db, user.id, tag_number=tag_number)
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)
    await message.answer(
        f"✅ **Пломба `#{tag_number}` проверена и подтверждена!**\nПояс не снимался.",
        parse_mode="Markdown",
    )

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "wear_comfort_init")
async def cb_wear_comfort_init(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⭐ **Оцените физический комфорт ношения пояса:**\n\n"
        "1 — Сильный дискомфорт / боль\n"
        "3 — Терпимо / привычно\n"
        "5 — Идеально / не ощущается",
        parse_mode="Markdown",
        reply_markup=get_wear_comfort_keyboard(),
    )
    await callback.answer()


@personal_router.callback_query(F.data.startswith("wear_score:"))
async def cb_wear_score_selected(callback: types.CallbackQuery, state: FSMContext):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return

    score = int(callback.data.split(":", 1)[1])

    async with async_session_factory() as db:
        session = await wear_svc.get_or_create_open_ended_session(db, user.id)
        session.last_comfort_score = score
        await db.commit()
        status = await wear_svc.get_wear_status(db, user.id)

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer(f"Комфорт отмечен: {score}/5")


@personal_router.callback_query(F.data == "wear_orgasm_init")
async def cb_wear_orgasm_init(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PersonalStates.waiting_for_wear_orgasm_notes)
    await callback.message.answer(
        "💥 **Отметка оргазма / эякуляции**\n\n"
        "Событие будет зафиксировано и внесено в Сексуальный журнал независимо от текущего статуса пояса.\n\n"
        "Введите краткий комментарий или отправьте `+` для быстрой отметки:",
        parse_mode="Markdown",
    )
    await callback.answer()


@personal_router.message(PersonalStates.waiting_for_wear_orgasm_notes)
async def msg_wear_orgasm_notes(message: types.Message, state: FSMContext):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await state.set_state(None)
        return

    notes = (message.text or "").strip()
    if notes in ("+", "-", ""):
        notes = "Фиксация оргазма через таймер ношения"

    async with async_session_factory() as db:
        orgasm_log, reactions = await wear_svc.record_orgasm_event(
            db,
            user.id,
            orgasms_count=1,
            notes=notes,
        )
        status = await wear_svc.get_wear_status(db, user.id)

    await state.set_state(None)
    await message.answer(
        "💥 **Оргазм зафиксирован и внесен в Сексуальный журнал!**",
        parse_mode="Markdown",
    )

    data = await state.get_data()
    is_agent_mode = data.get("wear_agent_mode", False)
    text, kb = _render_wear_card(status, is_agent_mode=is_agent_mode)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

