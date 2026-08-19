"""Telegram bot — aiogram 3.x, webhook/polling, real task generation & gamification."""

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from fastapi import APIRouter, Request
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.gamification.handler import on_task_completed, on_task_interrupted
from app.llm.pipeline import generate_task, get_active_llm_config
from app.llm.repair import JsonRepairError
from app.models.activity_log import ActivityLog
from app.models.progress import UserProgress
from app.models.session import ActivitySession
from app.models.user import User
from app.prefs import prefs_from_dict, raw_dict, sanitize_prefs
from app.timeutils import as_utc

logger = logging.getLogger(__name__)

# --- Bot setup ---
TG_BOT_TOKEN = getattr(settings, "tg_bot_token", None)
TG_WEBHOOK_SECRET = getattr(settings, "tg_webhook_secret", "change-me")
TG_WEBHOOK_PATH = "/tg/webhook"

bot: Bot | None = None
dp: Dispatcher | None = None
tg_router = APIRouter(prefix="/tg", tags=["telegram"])
main_router = Router()

if TG_BOT_TOKEN:
    bot = Bot(token=TG_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(main_router)

    # ── helpers ──────────────────────────────────────────────────────

    async def _get_user_by_chat(chat_id: int) -> User | None:
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
            return result.scalar_one_or_none()

    async def _get_user_progress(db, user_id: uuid.UUID) -> UserProgress | None:
        result = await db.execute(select(UserProgress).where(UserProgress.user_id == user_id))
        return result.scalar_one_or_none()

    async def _require_user(message: types.Message) -> User | None:
        """Check that the user is linked. Reply with help if not."""
        user = await _get_user_by_chat(message.chat.id)
        if user is None:
            await message.answer(
                "🔒 Your Telegram is not linked to an account yet.\n\n"
                'Go to your web profile → "Link Telegram" → copy the code → send:\n'
                "/link YOUR_CODE"
            )
        return user

    # ── /start ───────────────────────────────────────────────────────

    @main_router.message(Command("start"))
    async def cmd_start(message: types.Message):
        await message.answer(
            "👋 Welcome to **Practice Loop** Bot!\n\n"
            "🔗 *First time?* Link your account:\n"
            "1. Open your web profile\n"
            '2. Click "Link Telegram" → copy the 6‑character code\n'
            "3. Send `/link YOUR_CODE` here\n\n"
            "📋 *Commands:*\n"
            "/next — generate a task\n"
            "/tasks — your active tasks\n"
            "/done — mark a task complete\n"
            "/interrupt — interrupt a task (penalty!)\n"
            "/stats — XP, streak, points\n"
            "/session — session status\n"
            "/med — today's medication doses\n"
            "/health — daily check-in (mood/energy)\n"
            "/cycle — cycle phase & next period\n"
            "/care — due routines & course sessions\n"
            "/lock — active chastity session status\n"
            "/lock_start — start your latest draft\n"
            "/lock_stop — safety-stop the active session\n"
            "/lock_slots — unlock windows (open/close)\n"
            "/lock_tasks — required tasks (reveal/complete/skip)\n"
            "/lock_close — close window with a numbered seal\n"
            "/lock_tag — verify a numbered seal\n"
            "/settings — preferences",
            parse_mode="Markdown",
        )

    # ── /link ────────────────────────────────────────────────────────

    @main_router.message(Command("link"))
    async def cmd_link(message: types.Message):
        code = message.text.replace("/link", "").strip()
        if not code or len(code) < 4:
            await message.answer("Usage: /link YOUR_CODE\nFind the 6‑character code in your web profile.")
            return

        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.telegram_link_code == code.upper()))
            user = result.scalar_one_or_none()

            if user is None:
                await message.answer("❌ Invalid code. Check your web profile and try again.")
                return

            if user.telegram_link_code_expires and as_utc(user.telegram_link_code_expires) < datetime.now(UTC):
                await message.answer("⏰ Code expired. Generate a new one in your web profile.")
                return

            # Link the account
            user.telegram_chat_id = message.chat.id
            user.telegram_link_code = None
            user.telegram_link_code_expires = None
            db.add(user)
            await db.commit()

        await message.answer(
            f"✅ Linked! Welcome, {user.email}!\n\nUse /next to get your first task, or /stats to see your progress.",
        )

    # ── /next ────────────────────────────────────────────────────────

    @main_router.message(Command("next"))
    async def cmd_next(message: types.Message):
        user = await _require_user(message)
        if user is None:
            return

        async with async_session_factory() as db:
            config = await get_active_llm_config(db, user.id)
            if config is None:
                await message.answer("❌ No active LLM provider configured. Set one up in the web app.")
                return

            try:
                log = await generate_task(
                    db=db,
                    user_id=user.id,
                    llm_config=config,
                    session_id=None,
                    locale=user.locale,
                    llm_mode=prefs_from_dict(user.prefs).llm_mode,
                )
                await db.commit()
            except JsonRepairError:
                await message.answer("❌ LLM response could not be parsed. Try again.")
                return
            except ValueError as e:
                await message.answer(f"❌ {e}")
                return
            except Exception:
                logger.exception("LLM generate failed in bot /next")
                await message.answer("❌ LLM request failed. Check your provider config.")
                return

        # Build a compact task card
        name = log.selected_entity_name or "Task"
        params = log.selected_params or {}
        lines = [f"🎲 **{name}**"]
        if params.get("duration_min"):
            lines.append(f"⏱ {params['duration_min']}–{params.get('duration_max', params['duration_min'])} min")
        if params.get("intensity"):
            lines.append(f"⚡ Intensity: {params['intensity']}/5")
        if params.get("description"):
            lines.append(f"📝 _{params['description']}_")

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Done", callback_data=f"done:{log.id}"),
                    InlineKeyboardButton(text="⏹ Interrupt", callback_data=f"int:{log.id}"),
                ]
            ]
        )
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

    # ── /tasks ──────────────────────────────────────────────────────

    @main_router.message(Command("tasks"))
    async def cmd_tasks(message: types.Message):
        user = await _require_user(message)
        if user is None:
            return

        async with async_session_factory() as db:
            result = await db.execute(
                select(ActivityLog)
                .where(
                    ActivityLog.user_id == user.id,
                    ActivityLog.status == "planned",
                )
                .order_by(ActivityLog.created_at.desc())
                .limit(5)
            )
            active = result.scalars().all()

        if not active:
            await message.answer("📭 No active tasks. Use /next to generate one!")
            return

        for log in active:
            name = log.selected_entity_name or "Task"
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Done", callback_data=f"done:{log.id}"),
                        InlineKeyboardButton(text="⏹ Interrupt", callback_data=f"int:{log.id}"),
                    ]
                ]
            )
            created = log.created_at.strftime("%H:%M") if log.created_at else ""
            await message.answer(f"🎯 **{name}**\n_{created}_", parse_mode="Markdown", reply_markup=kb)

    # ── /done ────────────────────────────────────────────────────────

    @main_router.message(Command("done"))
    async def cmd_done(message: types.Message):
        user = await _require_user(message)
        if user is None:
            return

        async with async_session_factory() as db:
            result = await db.execute(
                select(ActivityLog)
                .where(
                    ActivityLog.user_id == user.id,
                    ActivityLog.status == "planned",
                )
                .order_by(ActivityLog.created_at.desc())
                .limit(1)
            )
            log = result.scalar_one_or_none()

            if log is None:
                await message.answer("📭 No active task to complete. Use /next first!")
                return

            log.status = "completed"
            db.add(log)
            await db.flush()
            gamification = await on_task_completed(db, user.id, log)
            await db.commit()

        lines = [
            "✅ Task completed! Great job! 🎉",
            f"⭐ +{gamification['xp_earned']} XP (total: {gamification['total_xp']}, level {gamification['level']})",
        ]
        if gamification["points_earned"]:
            lines.append(f"💰 +{gamification['points_earned']} points (balance: {gamification['points_balance']})")
        if gamification["leveled_up"]:
            lines.append("🆙 **LEVEL UP!**")
        if gamification["new_achievements"]:
            lines.append(f"🏆 {gamification['new_achievements']} new achievement(s)!")

        await message.answer("\n".join(lines), parse_mode="Markdown")

    # ── /interrupt ──────────────────────────────────────────────────

    @main_router.message(Command("interrupt"))
    async def cmd_interrupt(message: types.Message):
        user = await _require_user(message)
        if user is None:
            return

        async with async_session_factory() as db:
            result = await db.execute(
                select(ActivityLog)
                .where(
                    ActivityLog.user_id == user.id,
                    ActivityLog.status == "planned",
                )
                .order_by(ActivityLog.created_at.desc())
                .limit(1)
            )
            log = result.scalar_one_or_none()

            if log is None:
                await message.answer("📭 No active task to interrupt. Use /next first!")
                return

            name = log.selected_entity_name or "this task"
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Yes, interrupt ⚠️", callback_data=f"int_confirm:{log.id}"),
                        InlineKeyboardButton(text="Cancel", callback_data="int_cancel"),
                    ]
                ]
            )
            await message.answer(
                f"⚠️ Interrupt **{name}**?\nA penalty will be applied.",
                parse_mode="Markdown",
                reply_markup=kb,
            )

    # ── Inline handlers for done / interrupt ────────────────────────

    @main_router.callback_query(F.data.startswith("done:"))
    async def inline_done(callback: types.CallbackQuery):
        log_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        async with async_session_factory() as db:
            result = await db.execute(
                select(ActivityLog).where(ActivityLog.id == log_id, ActivityLog.user_id == user.id)
            )
            log = result.scalar_one_or_none()
            if log is None:
                await callback.answer("Task not found.", show_alert=True)
                return
            if log.status != "planned":  # State integrity: no reward after interrupt/complete
                await callback.answer("Task already finished.", show_alert=True)
                return

            log.status = "completed"
            db.add(log)
            await db.flush()
            gamification = await on_task_completed(db, user.id, log)
            await db.commit()

        name = log.selected_entity_name or "Task"
        lines = [
            f"✅ **{name}** — done!",
            f"⭐ +{gamification['xp_earned']} XP",
        ]
        if gamification["points_earned"]:
            lines.append(f"💰 +{gamification['points_earned']} points")
        if gamification["leveled_up"]:
            lines.append("🆙 Level up!")

        await callback.message.edit_text("\n".join(lines), parse_mode="Markdown")
        await callback.answer("Completed! 🎉")

    @main_router.callback_query(F.data.startswith("int:"))
    async def inline_interrupt_prompt(callback: types.CallbackQuery):
        """Show confirmation for interrupt (from /tasks list)."""
        log_id = uuid.UUID(callback.data.split(":", 1)[1])

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Yes, interrupt ⚠️", callback_data=f"int_confirm:{log_id}"),
                    InlineKeyboardButton(text="Cancel", callback_data="int_cancel"),
                ]
            ]
        )
        await callback.message.edit_text(
            callback.message.text + "\n\n⚠️ Really interrupt?",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        await callback.answer()

    @main_router.callback_query(F.data == "int_cancel")
    async def inline_interrupt_cancel(callback: types.CallbackQuery):
        await callback.message.edit_text("✅ Continue with your task!")
        await callback.answer()

    @main_router.callback_query(F.data.startswith("int_confirm:"))
    async def inline_interrupt_confirm(callback: types.CallbackQuery):
        log_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        async with async_session_factory() as db:
            result = await db.execute(
                select(ActivityLog).where(ActivityLog.id == log_id, ActivityLog.user_id == user.id)
            )
            log = result.scalar_one_or_none()
            if log is None:
                await callback.answer("Task not found.", show_alert=True)
                return
            if log.status != "planned":  # State integrity: no re-interrupt of finished tasks
                await callback.answer("Task already finished.", show_alert=True)
                return

            log.status = "stopped"
            db.add(log)
            await db.flush()
            penalty = await on_task_interrupted(db, user.id, log)
            await db.commit()

        name = log.selected_entity_name or "Task"
        lines = [
            f"⏹ **{name}** — stopped",
            f"🔻 -{penalty['xp_penalty']} XP (escalation ×{penalty['escalation']})",
        ]
        if penalty.get("xp_penalty", 0) > 0:
            lines.append("💡 Check /stats for your current balance")

        await callback.message.edit_text("\n".join(lines), parse_mode="Markdown")
        await callback.answer("Interrupted ⚠️")

    # ── /stats ──────────────────────────────────────────────────────

    @main_router.message(Command("stats"))
    async def cmd_stats(message: types.Message):
        user = await _require_user(message)
        if user is None:
            return

        async with async_session_factory() as db:
            progress = await _get_user_progress(db, user.id)

        if progress is None:
            await message.answer("📊 No stats yet. Complete your first task with /next!")
            return

        lines = [
            "📊 **Your Stats**",
            f"⭐ XP: {progress.xp} (level {progress.level})",
            f"✅ Completed: {progress.total_completed}",
            f"⏹ Interrupted: {progress.total_interrupted}",
            f"🔥 Streak: {progress.current_streak} days (best: {progress.longest_streak})",
            f"🎯 Combo: ×{progress.combo_count}",
        ]
        if progress.points_balance:
            lines.append(f"💰 Points: {progress.points_balance}")

        await message.answer("\n".join(lines), parse_mode="Markdown")

    # ── /session ────────────────────────────────────────────────────

    @main_router.message(Command("session"))
    async def cmd_session(message: types.Message):
        user = await _require_user(message)
        if user is None:
            return

        async with async_session_factory() as db:
            result = await db.execute(
                select(ActivitySession)
                .where(ActivitySession.owner_id == user.id)
                .order_by(ActivitySession.created_at.desc())
                .limit(1)
            )
            session = result.scalar_one_or_none()

        if session is None:
            await message.answer(
                "🎯 No active session.\n"
                "Create one in the web app to track activities together.\n"
                "Use /next to generate tasks outside of sessions."
            )
            return

        status_emoji = {"created": "🆕", "active": "▶️", "ended": "⏹"}
        emoji = status_emoji.get(session.status, "❓")
        await message.answer(
            f"{emoji} Session: **{session.status}**\n"
            f"Created: {session.created_at.strftime('%Y-%m-%d %H:%M') if session.created_at else '-'}\n"
            "Manage in the web app.",
            parse_mode="Markdown",
        )

    # ── /settings ───────────────────────────────────────────────────

    def _settings_view(user: User) -> tuple[str, InlineKeyboardMarkup]:
        """Build the settings text + inline keyboard reflecting current prefs."""
        prefs = prefs_from_dict(user.prefs)
        text = (
            "⚙️ *Settings*\n"
            f"Language: {user.locale.upper()}\n"
            f"Discretion: {prefs.discretion_mode}\n"
            f"LLM mode: {prefs.llm_mode}\n"
            "\nTap to change:"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🇬🇧 EN", callback_data="lang:en"),
                    InlineKeyboardButton(text="🇷🇺 RU", callback_data="lang:ru"),
                ],
                [
                    InlineKeyboardButton(text="Discretion: Off", callback_data="disc:off"),
                    InlineKeyboardButton(text="Always", callback_data="disc:always"),
                    InlineKeyboardButton(text="Schedule", callback_data="disc:schedule"),
                ],
                [
                    InlineKeyboardButton(text="LLM: Safe", callback_data="llm:safe"),
                    InlineKeyboardButton(text="Expanded", callback_data="llm:expanded"),
                ],
            ]
        )
        return text, kb

    async def _rerender_settings(callback: types.CallbackQuery) -> None:
        async with async_session_factory() as db:
            u = (
                await db.execute(select(User).where(User.telegram_chat_id == callback.message.chat.id))
            ).scalar_one_or_none()
            if u is None:
                await callback.answer("Account not linked.", show_alert=True)
                return
            text, kb = _settings_view(u)
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)

    async def _fetch_by_chat(chat_id: int):
        async with async_session_factory() as db:
            return (await db.execute(select(User).where(User.telegram_chat_id == chat_id))).scalar_one_or_none()

    @main_router.message(Command("settings"))
    async def cmd_settings(message: types.Message):
        user = await _require_user(message)
        if user is None:
            return
        u = await _fetch_by_chat(message.chat.id)
        if u is None:
            await message.answer("Account not linked.")
            return
        text, kb = _settings_view(u)
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)

    @main_router.callback_query(F.data.startswith("lang:"))
    async def inline_lang(callback: types.CallbackQuery):
        new_locale = callback.data.split(":", 1)[1]
        async with async_session_factory() as db:
            u = (
                await db.execute(select(User).where(User.telegram_chat_id == callback.message.chat.id))
            ).scalar_one_or_none()
            if u is None:
                await callback.answer("Account not linked.", show_alert=True)
                return
            u.locale = new_locale
            db.add(u)
            await db.commit()
        await _rerender_settings(callback)
        await callback.answer()

    @main_router.callback_query(F.data.startswith("disc:"))
    async def inline_disc(callback: types.CallbackQuery):
        mode = callback.data.split(":", 1)[1]
        async with async_session_factory() as db:
            u = (
                await db.execute(select(User).where(User.telegram_chat_id == callback.message.chat.id))
            ).scalar_one_or_none()
            if u is None:
                await callback.answer("Account not linked.", show_alert=True)
                return
            raw = sanitize_prefs(raw_dict(u.prefs))
            raw["discretion"]["mode"] = mode
            u.prefs = raw
            db.add(u)
            await db.commit()
        await _rerender_settings(callback)
        await callback.answer()

    @main_router.callback_query(F.data.startswith("llm:"))
    async def inline_llm(callback: types.CallbackQuery):
        mode = callback.data.split(":", 1)[1]
        async with async_session_factory() as db:
            u = (
                await db.execute(select(User).where(User.telegram_chat_id == callback.message.chat.id))
            ).scalar_one_or_none()
            if u is None:
                await callback.answer("Account not linked.", show_alert=True)
                return
            raw = sanitize_prefs(raw_dict(u.prefs))
            raw["llm_mode"] = mode
            u.prefs = raw
            db.add(u)
            await db.commit()
        await _rerender_settings(callback)
        await callback.answer()

    # ── Lock Timer commands (Personal, Step 8) ───────────────────────

    def _fmt_duration(delta: timedelta) -> str:
        total = max(0, int(delta.total_seconds()))
        days, rem = divmod(total, 86400)
        hours, rem = divmod(rem, 3600)
        mins = rem // 60
        if days:
            return f"{days}d {hours}h {mins}m"
        if hours:
            return f"{hours}h {mins}m"
        return f"{mins}m"

    @main_router.message(Command("lock"))
    async def cmd_lock(message: types.Message):
        """Status of the active lock session: since, unlock at, remaining, next windows."""
        user = await _require_user(message)
        if user is None:
            return
        if not getattr(settings, "locktimer_core_enabled", False):
            await message.answer("⏳ Lock Timer is not enabled on this instance.")
            return

        from app.locktimer.repositories import (
            get_active_session,
            list_slot_occurrences,
            list_task_occurrences,
        )

        async with async_session_factory() as db:
            session = await get_active_session(db, user.id)
            if session is None:
                await message.answer(
                    "🔓 No active chastity session.\n"
                    "Create a draft in the web app (/locktimer), or send /lock_start to start your latest draft."
                )
                return
            slot_occs = await list_slot_occurrences(db, session.id, limit=5)
            task_occs = await list_task_occurrences(db, session.id, limit=5)

        lines = ["🔒 *Active Chastity Session*"]
        if session.started_at:
            started = as_utc(session.started_at)
            lines.append(f"Locked since: {started.strftime('%Y-%m-%d %H:%M')} UTC")
        end = session.effective_end_at or session.max_end_at
        if end:
            end_utc = as_utc(end)
            remaining = end_utc - datetime.now(UTC)
            lines.append(f"Unlock at: {end_utc.strftime('%Y-%m-%d %H:%M')} UTC")
            lines.append(f"Remaining: {_fmt_duration(remaining)}")
        lines.append(f"Timezone: {session.timezone}")
        next_slots = [o for o in slot_occs if o.state == "pending" and o.planned_open_at is not None]
        if next_slots:
            nxt = as_utc(next_slots[0].planned_open_at)
            lines.append(f"Next unlock window: {nxt.strftime('%Y-%m-%d %H:%M')} UTC")
        open_tasks = [o for o in task_occs if o.state in ("scheduled", "visible", "submitted")]
        if open_tasks:
            lines.append(f"Pending tasks: {len(open_tasks)}")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🛑 Safety Stop", callback_data=f"lock_stop:{session.id}")]]
        )
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

    @main_router.message(Command("lock_start"))
    async def cmd_lock_start(message: types.Message):
        """Start the latest draft lock session (with confirmation)."""
        user = await _require_user(message)
        if user is None:
            return
        if not getattr(settings, "locktimer_core_enabled", False):
            await message.answer("⏳ Lock Timer is not enabled on this instance.")
            return

        from app.locktimer import enums as e
        from app.models.locktimer import LockSession

        async with async_session_factory() as db:
            result = await db.execute(
                select(LockSession)
                .where(LockSession.owner_id == user.id, LockSession.state == e.SESSION_DRAFT)
                .order_by(LockSession.updated_at.desc())
                .limit(1)
            )
            draft = result.scalar_one_or_none()

        if draft is None:
            await message.answer("📭 No draft chastity session. Create one in the web app (/locktimer).")
            return

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔒 Start", callback_data=f"lock_start_confirm:{draft.id}"),
                    InlineKeyboardButton(text="Cancel", callback_data="lock_cancel"),
                ]
            ]
        )
        await message.answer(
            f"Start chastity session `{str(draft.id)[:8]}`? Rules will be frozen.",
            parse_mode="Markdown",
            reply_markup=kb,
        )

    @main_router.message(Command("lock_stop"))
    async def cmd_lock_stop(message: types.Message):
        """Safety-stop the active lock session (with confirmation)."""
        user = await _require_user(message)
        if user is None:
            return
        if not getattr(settings, "locktimer_core_enabled", False):
            await message.answer("⏳ Lock Timer is not enabled on this instance.")
            return

        from app.locktimer.repositories import get_active_session

        async with async_session_factory() as db:
            session = await get_active_session(db, user.id)

        if session is None:
            await message.answer("🔓 No active chastity session.")
            return

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⚠️ Yes, safety stop", callback_data=f"lock_stop_confirm:{session.id}"),
                    InlineKeyboardButton(text="Cancel", callback_data="lock_cancel"),
                ]
            ]
        )
        await message.answer(
            "⚠️ Safety stop the active session? Future unlock windows will be cancelled. This cannot be undone.",
            reply_markup=kb,
        )

    @main_router.callback_query(F.data.startswith("lock_start_confirm:"))
    async def inline_lock_start(callback: types.CallbackQuery):
        session_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.locktimer.services.session import start_session

        async with async_session_factory() as db:
            try:
                await start_session(db, session_id=session_id, owner_id=user.id)
                await db.commit()
            except ValueError as exc:
                await callback.answer(str(exc), show_alert=True)
                return

        await callback.message.edit_text("🔒 Session started. Send /lock to see status.")
        await callback.answer("Locked!")

    @main_router.callback_query(F.data.startswith("lock_stop_confirm:"))
    async def inline_lock_stop(callback: types.CallbackQuery):
        session_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.locktimer.services.session import safety_stop

        async with async_session_factory() as db:
            try:
                await safety_stop(db, session_id=session_id, owner_id=user.id, reason_code="user_requested")
                await db.commit()
            except ValueError as exc:
                await callback.answer(str(exc), show_alert=True)
                return

        await callback.message.edit_text("🔓 Session stopped. The device is available again.")
        await callback.answer("Stopped")

    @main_router.callback_query(F.data == "lock_cancel")
    async def inline_lock_cancel(callback: types.CallbackQuery):
        await callback.message.edit_text("Cancelled.")
        await callback.answer()

    # ── Lock Timer: slot/task management + seal verification (ADR-096) ──

    def _task_title(occ) -> str:
        snap = occ.occurrence_snapshot or {}
        return snap.get("title") or snap.get("name") or "Task"

    async def _get_slot_occ(db, occ_id: uuid.UUID, owner_id: uuid.UUID):
        from app.models.locktimer import LockSession, LockSlotOccurrence

        occ = await db.get(LockSlotOccurrence, occ_id)
        if occ is None:
            return None
        session = await db.get(LockSession, occ.session_id)
        if session is None or session.owner_id != owner_id:
            return None
        return occ

    async def _get_task_occ(db, occ_id: uuid.UUID, owner_id: uuid.UUID):
        from app.models.locktimer import LockSession, LockTaskOccurrence

        occ = await db.get(LockTaskOccurrence, occ_id)
        if occ is None:
            return None
        session = await db.get(LockSession, occ.session_id)
        if session is None or session.owner_id != owner_id:
            return None
        return occ

    @main_router.message(Command("lock_slots"))
    async def cmd_lock_slots(message: types.Message):
        user = await _require_user(message)
        if user is None:
            return
        if not getattr(settings, "locktimer_core_enabled", False):
            await message.answer("⏳ Lock Timer is not enabled on this instance.")
            return

        from app.locktimer.repositories import get_active_session, list_slot_occurrences

        async with async_session_factory() as db:
            session = await get_active_session(db, user.id)
            if session is None:
                await message.answer("🔓 No active chastity session.")
                return
            slots = await list_slot_occurrences(db, session.id, limit=10)

        open_slots = [o for o in slots if o.state == "open"]
        upcoming = [o for o in slots if o.state in ("pending", "eligible") and o.planned_open_at]
        lines = ["🔒 *Unlock Windows*"]
        kb_rows = []
        for o in upcoming[:6]:
            when = as_utc(o.planned_open_at).strftime("%m-%d %H:%M") if o.planned_open_at else "?"
            lines.append(f"⏳ {when}")
            kb_rows.append([InlineKeyboardButton(text=f"Open {when}", callback_data=f"slot_open:{o.id}")])
        for o in open_slots[:3]:
            due = as_utc(o.close_due_at).strftime("%H:%M") if o.close_due_at else "?"
            lines.append(f"🔓 Open (close due {due})")
            kb_rows.append([InlineKeyboardButton(text="Close", callback_data=f"slot_close:{o.id}")])
        if not kb_rows:
            lines.append("No upcoming or open windows.")
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

    @main_router.message(Command("lock_tasks"))
    async def cmd_lock_tasks(message: types.Message):
        user = await _require_user(message)
        if user is None:
            return
        if not getattr(settings, "locktimer_core_enabled", False):
            await message.answer("⏳ Lock Timer is not enabled on this instance.")
            return

        from app.locktimer.repositories import get_active_session, list_task_occurrences

        async with async_session_factory() as db:
            session = await get_active_session(db, user.id)
            if session is None:
                await message.answer("🔓 No active chastity session.")
                return
            tasks = await list_task_occurrences(db, session.id, limit=10)

        active = [t for t in tasks if t.state in ("scheduled", "visible", "submitted")]
        lines = ["🎯 *Required Tasks*"]
        kb_rows = []
        for t in active[:6]:
            lines.append(f"• {_task_title(t)}")
            row = []
            if t.state == "scheduled":
                row.append(InlineKeyboardButton(text="Reveal", callback_data=f"task_reveal:{t.id}"))
            if t.state in ("scheduled", "visible"):
                row.append(InlineKeyboardButton(text="Complete", callback_data=f"task_complete:{t.id}"))
                row.append(InlineKeyboardButton(text="Skip", callback_data=f"task_skip:{t.id}"))
            if t.state == "submitted":
                row.append(InlineKeyboardButton(text="Complete", callback_data=f"task_complete:{t.id}"))
            if row:
                kb_rows.append(row)
        if not kb_rows:
            lines.append("No active tasks.")
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

    @main_router.message(Command("lock_close"))
    async def cmd_lock_close(message: types.Message):
        """Close the open window, optionally with a numbered seal: /lock_close A-0042."""
        user = await _require_user(message)
        if user is None:
            return
        if not getattr(settings, "locktimer_core_enabled", False):
            await message.answer("⏳ Lock Timer is not enabled on this instance.")
            return

        tag = message.text.replace("/lock_close", "").strip() or None

        from app.locktimer.repositories import get_active_session, list_slot_occurrences
        from app.locktimer.services.execution import close_slot
        from app.models.locktimer import LockSlotRule

        async with async_session_factory() as db:
            session = await get_active_session(db, user.id)
            if session is None:
                await message.answer("🔓 No active chastity session.")
                return
            slots = await list_slot_occurrences(db, session.id)
            open_slots = [o for o in slots if o.state == "open"]
            if not open_slots:
                await message.answer("No open window to close.")
                return
            occ = open_slots[0]
            rule = await db.get(LockSlotRule, occ.rule_id)
            if rule and rule.require_tag and not tag:
                await message.answer("🔐 This window requires a numbered seal.\nSend:\n/lock_close <seal_number>")
                return
            try:
                await close_slot(db, occurrence=occ, owner_id=user.id, tag_number=tag)
                await db.commit()
            except ValueError as exc:
                await message.answer(f"❌ {exc}")
                return

        suffix = f" with seal #{tag}" if tag else ""
        await message.answer(f"🔒 Window closed{suffix}.")

    @main_router.message(Command("lock_tag"))
    async def cmd_lock_tag(message: types.Message):
        """Verify a numbered seal: /lock_tag A-0042."""
        user = await _require_user(message)
        if user is None:
            return
        if not getattr(settings, "locktimer_core_enabled", False):
            await message.answer("⏳ Lock Timer is not enabled on this instance.")
            return

        tag = message.text.replace("/lock_tag", "").strip()
        if not tag:
            await message.answer("Usage: /lock_tag <seal_number>")
            return

        from app.locktimer.repositories import get_active_session
        from app.locktimer.services.tags import lookup_tag

        async with async_session_factory() as db:
            session = await get_active_session(db, user.id)
            if session is None:
                await message.answer("🔓 No active chastity session.")
                return
            try:
                result = await lookup_tag(db, tag_number=tag, session_id=session.id, owner_id=user.id)
            except ValueError as exc:
                await message.answer(f"❌ {exc}")
                return

        if result is None:
            await message.answer(f"❌ No window was closed with seal #{tag}.")
        else:
            closed = result.get("actual_closed_at") or "?"
            await message.answer(f"✅ Seal #{tag} matches a closed window.\nClosed: {closed}")

    @main_router.callback_query(F.data.startswith("slot_open:"))
    async def inline_slot_open(callback: types.CallbackQuery):
        occ_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.locktimer.services.execution import open_slot

        async with async_session_factory() as db:
            occ = await _get_slot_occ(db, occ_id, user.id)
            if occ is None:
                await callback.answer("Window not found.", show_alert=True)
                return
            try:
                await open_slot(db, occurrence=occ, owner_id=user.id)
                await db.commit()
            except ValueError as exc:
                await callback.answer(str(exc), show_alert=True)
                return

        await callback.message.edit_text("🔓 Window opened. Send /lock to see status.")
        await callback.answer("Opened")

    @main_router.callback_query(F.data.startswith("slot_close:"))
    async def inline_slot_close_prompt(callback: types.CallbackQuery):
        occ_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.models.locktimer import LockSlotRule

        async with async_session_factory() as db:
            occ = await _get_slot_occ(db, occ_id, user.id)
            if occ is None:
                await callback.answer("Window not found.", show_alert=True)
                return
            rule = await db.get(LockSlotRule, occ.rule_id)
            requires_tag = bool(rule and rule.require_tag)

        if requires_tag:
            await callback.message.edit_text(
                "🔐 This window requires a numbered seal.\nSend:\n/lock_close <seal_number>"
            )
        else:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Yes, close", callback_data=f"slot_close_confirm:{occ_id}"),
                        InlineKeyboardButton(text="Cancel", callback_data="lock_cancel"),
                    ]
                ]
            )
            await callback.message.edit_text("Close this window?", reply_markup=kb)
        await callback.answer()

    @main_router.callback_query(F.data.startswith("slot_close_confirm:"))
    async def inline_slot_close_confirm(callback: types.CallbackQuery):
        occ_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.locktimer.services.execution import close_slot

        async with async_session_factory() as db:
            occ = await _get_slot_occ(db, occ_id, user.id)
            if occ is None:
                await callback.answer("Window not found.", show_alert=True)
                return
            try:
                await close_slot(db, occurrence=occ, owner_id=user.id, tag_number=None)
                await db.commit()
            except ValueError as exc:
                await callback.answer(str(exc), show_alert=True)
                return

        await callback.message.edit_text("🔒 Window closed.")
        await callback.answer("Closed")

    @main_router.callback_query(F.data.startswith("task_reveal:"))
    async def inline_task_reveal(callback: types.CallbackQuery):
        occ_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.locktimer.services.execution import reveal_task

        async with async_session_factory() as db:
            occ = await _get_task_occ(db, occ_id, user.id)
            if occ is None:
                await callback.answer("Task not found.", show_alert=True)
                return
            try:
                await reveal_task(db, occurrence=occ, owner_id=user.id)
                await db.commit()
            except ValueError as exc:
                await callback.answer(str(exc), show_alert=True)
                return

        await callback.message.edit_text("📖 Task revealed. Send /lock_tasks to act on it.")
        await callback.answer("Revealed")

    @main_router.callback_query(F.data.startswith("task_complete:"))
    async def inline_task_complete(callback: types.CallbackQuery):
        occ_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.locktimer.services.execution import complete_task, submit_task

        async with async_session_factory() as db:
            occ = await _get_task_occ(db, occ_id, user.id)
            if occ is None:
                await callback.answer("Task not found.", show_alert=True)
                return
            try:
                if occ.state == "visible":
                    occ = await submit_task(db, occurrence=occ, owner_id=user.id)
                await complete_task(db, occurrence=occ, owner_id=user.id)
                await db.commit()
            except ValueError as exc:
                await callback.answer(str(exc), show_alert=True)
                return

        await callback.message.edit_text("✅ Task completed.")
        await callback.answer("Completed")

    @main_router.callback_query(F.data.startswith("task_skip:"))
    async def inline_task_skip(callback: types.CallbackQuery):
        occ_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.locktimer.services.execution import skip_task

        async with async_session_factory() as db:
            occ = await _get_task_occ(db, occ_id, user.id)
            if occ is None:
                await callback.answer("Task not found.", show_alert=True)
                return
            try:
                await skip_task(db, occurrence=occ, owner_id=user.id)
                await db.commit()
            except ValueError as exc:
                await callback.answer(str(exc), show_alert=True)
                return

        await callback.message.edit_text("⏭ Task skipped.")
        await callback.answer("Skipped")

    # ── Personal contour: medication / health / cycle / care (ADR-097) ──

    @main_router.message(Command("med"))
    async def cmd_med(message: types.Message):
        """Today's medication doses with inline 'Taken' buttons (records intake + adherence XP)."""
        user = await _require_user(message)
        if user is None:
            return

        from app.api.medication import _schedule_summary

        async with async_session_factory() as db:
            summary = await _schedule_summary(db, user.id)

        due = summary.get("due", [])
        if not due:
            await message.answer("💊 No medication doses due today. All caught up!")
            return

        lines = ["💊 *Medication Today*"]
        kb_rows = []
        for d in due[:8]:
            lines.append(f"• {d['medication_name']} — {d['dose']} ({d['pending']} left)")
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✅ Taken: {d['medication_name'][:22]}",
                        callback_data=f"med_take:{d['id']}",
                    )
                ]
            )
        if summary.get("expiring"):
            lines.append("\n⚠️ *Expiring soon:*")
            for e in summary["expiring"][:3]:
                lines.append(f"• {e['medication_name']} ({e['days']}d)")
        if summary.get("low_stock"):
            lines.append("\n📉 *Low stock:*")
            for item in summary["low_stock"][:3]:
                lines.append(f"• {item['medication_name']} ({item['quantity']:g})")
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

    @main_router.callback_query(F.data.startswith("med_take:"))
    async def inline_med_take(callback: types.CallbackQuery):
        schedule_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.gamification.medication import on_medication_taken
        from app.models.medication import MedIntake, MedSchedule

        async with async_session_factory() as db:
            sched = (
                await db.execute(
                    select(MedSchedule).where(MedSchedule.id == schedule_id, MedSchedule.user_id == user.id)
                )
            ).scalar_one_or_none()
            if sched is None:
                await callback.answer("Schedule not found.", show_alert=True)
                return
            name = sched.medication.name if sched.medication else "Medication"
            db.add(
                MedIntake(
                    user_id=user.id,
                    medication_id=sched.medication_id,
                    schedule_id=sched.id,
                    scheduled_at=datetime.now(UTC),
                    taken_at=datetime.now(UTC),
                    status="taken",
                    quantity_taken=sched.dose_quantity,
                )
            )
            await db.flush()
            result = await on_medication_taken(db, user.id, name, on_time=True)
            await db.commit()

        text = f"✅ {name} taken."
        if result.get("xp_earned"):
            text += f"\n⭐ +{result['xp_earned']} XP"
        if result.get("new_achievements"):
            text += f"\n🏆 {result['new_achievements']} new achievement(s)!"
        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer("Taken! 💊")

    def _health_view(state, cycle: dict) -> tuple[str, InlineKeyboardMarkup]:
        """Build the health check-in text + inline mood/energy keyboard."""
        lines = ["🩺 *Health Check-in*"]
        if state is not None:
            lines.append(f"Mood: {'⭐' * state.mood if state.mood else '—'}")
            lines.append(f"Energy: {'⚡' * state.energy if state.energy else '—'}")
            lines.append(f"Sleep: {state.sleep_hours if state.sleep_hours is not None else '—'} h")
        else:
            lines.append("No check-in yet today.")
        if cycle.get("phase"):
            lines.append(f"Cycle: {cycle['phase']} (day {cycle['day_of_cycle']})")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"Mood {i}", callback_data=f"health_mood:{i}") for i in range(1, 6)],
                [InlineKeyboardButton(text=f"Energy {i}", callback_data=f"health_energy:{i}") for i in range(1, 6)],
            ]
        )
        return "\n".join(lines), kb

    @main_router.message(Command("health"))
    async def cmd_health(message: types.Message):
        """Today's health check-in status with inline mood/energy buttons."""
        user = await _require_user(message)
        if user is None:
            return

        from app.api.health import _get_cycle_context
        from app.models.health import HealthState

        today = datetime.now(UTC).date()
        async with async_session_factory() as db:
            state = (
                await db.execute(
                    select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == today)
                )
            ).scalar_one_or_none()
            cycle = await _get_cycle_context(db, user.id)

        text, kb = _health_view(state, cycle)
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)

    async def _set_health_scale(callback: types.CallbackQuery, field: str) -> None:
        value = int(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.models.health import HealthState

        today = datetime.now(UTC).date()
        async with async_session_factory() as db:
            row = (
                await db.execute(
                    select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == today)
                )
            ).scalar_one_or_none()
            if row is None:
                row = HealthState(user_id=user.id, event_date=today)
                db.add(row)
            setattr(row, field, value)
            await db.commit()

        label = "Mood" if field == "mood" else "Energy"
        await callback.answer(f"{label} set to {value}")

    @main_router.callback_query(F.data.startswith("health_mood:"))
    async def inline_health_mood(callback: types.CallbackQuery):
        await _set_health_scale(callback, "mood")

    @main_router.callback_query(F.data.startswith("health_energy:"))
    async def inline_health_energy(callback: types.CallbackQuery):
        await _set_health_scale(callback, "energy")

    @main_router.message(Command("cycle"))
    async def cmd_cycle(message: types.Message):
        """Estimated cycle phase, day of cycle, and next period date."""
        user = await _require_user(message)
        if user is None:
            return

        from app.api.health import _get_cycle_context

        async with async_session_factory() as db:
            cycle = await _get_cycle_context(db, user.id)

        if not cycle.get("phase"):
            await message.answer("🌸 No cycle data yet. Add a bleeding event in the web app (/health) to start.")
            return

        settings = cycle.get("settings") or {}
        cl = settings.get("cycle_length", 28) or 28
        day = cycle["day_of_cycle"]
        today = datetime.now(UTC).date()
        next_period = today + timedelta(days=cl - day + 1)

        lines = [
            "🌸 *Cycle*",
            f"Phase: {cycle['phase']} (estimated)",
            f"Day {day} of {cl}",
            f"Next period (est.): {next_period.strftime('%Y-%m-%d')}",
        ]
        await message.answer("\n".join(lines), parse_mode="Markdown")

    @main_router.message(Command("care"))
    async def cmd_care(message: types.Message):
        """Care routines due today + course sessions, with inline 'Done' buttons."""
        user = await _require_user(message)
        if user is None:
            return

        from app.models.care import CareCourse, CareEntry, CareRoutine

        today = datetime.now(UTC).date()
        async with async_session_factory() as db:
            routines = (await db.execute(select(CareRoutine).where(CareRoutine.user_id == user.id))).scalars().all()
            entries = (await db.execute(select(CareEntry).where(CareEntry.user_id == user.id))).scalars().all()
            courses = (
                (
                    await db.execute(
                        select(CareCourse).where(CareCourse.user_id == user.id, CareCourse.status == "active")
                    )
                )
                .scalars()
                .all()
            )

        last_entry: dict[str, date] = {}
        for e in entries:
            if e.routine_id is None:
                continue
            key = str(e.routine_id)
            if key not in last_entry or e.entry_date > last_entry[key]:
                last_entry[key] = e.entry_date

        lines = ["🧴 *Care*"]
        kb_rows: list[list[InlineKeyboardButton]] = []
        due = [
            r
            for r in routines
            if r.frequency_days
            and (last_entry.get(str(r.id)) is None or (today - last_entry[str(r.id)]).days >= r.frequency_days)
        ]
        if due:
            lines.append("\n*Due routines:*")
            for r in due[:6]:
                lines.append(f"• {r.name} (every {r.frequency_days}d)")
                kb_rows.append(
                    [InlineKeyboardButton(text=f"✅ Done: {r.name[:22]}", callback_data=f"care_done:{r.id}")]
                )
        else:
            lines.append("\nNo routines due today.")

        for c in courses:
            pending = sorted((s for s in c.sessions if s.status == "pending"), key=lambda s: s.scheduled_date)
            if not pending:
                continue
            nxt = pending[0]
            lines.append(f"📅 {c.name}: session {nxt.session_number}/{c.total_sessions} on {nxt.scheduled_date}")
            if nxt.scheduled_date <= today + timedelta(days=2):
                kb_rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"✅ Session: {c.name[:22]}",
                            callback_data=f"care_course_done:{nxt.id}",
                        )
                    ]
                )

        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

    @main_router.callback_query(F.data.startswith("care_done:"))
    async def inline_care_done(callback: types.CallbackQuery):
        routine_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.api.care import _cycle_snapshot
        from app.models.care import CareEntry, CareRoutine

        today = datetime.now(UTC).date()
        async with async_session_factory() as db:
            routine = (
                await db.execute(
                    select(CareRoutine).where(CareRoutine.id == routine_id, CareRoutine.user_id == user.id)
                )
            ).scalar_one_or_none()
            if routine is None:
                await callback.answer("Routine not found.", show_alert=True)
                return
            cycle_phase, cycle_day = await _cycle_snapshot(db, user.id, today)
            db.add(
                CareEntry(
                    user_id=user.id,
                    routine_id=routine.id,
                    entry_date=today,
                    cycle_phase=cycle_phase,
                    cycle_day=cycle_day,
                )
            )
            await db.commit()

        await callback.message.edit_text(f"✅ {routine.name} logged for today.")
        await callback.answer("Done! 🧴")

    @main_router.callback_query(F.data.startswith("care_course_done:"))
    async def inline_care_course_done(callback: types.CallbackQuery):
        session_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.models.care import CareCourse, CareCourseSession

        async with async_session_factory() as db:
            sess = await db.get(CareCourseSession, session_id)
            if sess is None:
                await callback.answer("Session not found.", show_alert=True)
                return
            course = await db.get(CareCourse, sess.course_id)
            if course is None or course.user_id != user.id:
                await callback.answer("Session not found.", show_alert=True)
                return
            sess.status = "done"
            sess.completed_at = datetime.now(UTC)
            db.add(sess)
            await db.commit()

        await callback.message.edit_text(f"✅ Session {sess.session_number} of {course.name} done.")
        await callback.answer("Done! 📅")

    # ── Notification sender (public API for the rest of the app) ──────


async def send_telegram_notification(chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message to a Telegram user. Returns True on success."""
    if bot is None:
        return False
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        return True
    except Exception:
        logger.warning(f"Failed to send TG notification to chat {chat_id}", exc_info=True)
        return False

    # ── Telegram Bot v3: Keyholder, Aftercare & Report ───────────────

    @main_router.message(Command("keyholder"))
    @main_router.message(Command("chastity"))
    async def cmd_chastity_keyholder(message: types.Message):
        """Telegram v3 Chastity & Keyholder status with inline action buttons."""
        user = await _require_user(message)
        if user is None:
            return

        from app.models.locktimer import LockSession

        async with async_session_factory() as db:
            session = (
                await db.execute(
                    select(LockSession)
                    .where(LockSession.owner_id == user.id, LockSession.status == "active")
                    .order_by(LockSession.started_at.desc())
                )
            ).scalar_one_or_none()

            if not session:
                await message.answer("🔒 *Chastity Suite*: No active lock session.", parse_mode="Markdown")
                return

            ext_count = len(session.extension_history or [])
            lines = [
                "🔒 *Chastity & Keyholder Status*",
                f"Session ID: `{str(session.id)[:8]}`",
                f"Status: *{session.status.upper()}*",
                f"Keyholder Type: *{session.keyholder_type or 'ai'}*",
                f"Extensions Granted: {ext_count}",
                f"Health Paused: {'YES ⏸️' if session.is_health_paused else 'No'}",
            ]

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🤖 AI Keyholder Evaluation",
                            callback_data=f"keyholder_eval:{session.id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🧴 Request Aftercare",
                            callback_data="aftercare_gen",
                        )
                    ],
                ]
            )

            await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

    @main_router.callback_query(F.data.startswith("keyholder_eval:"))
    async def inline_keyholder_eval(callback: types.CallbackQuery):
        session_id = uuid.UUID(callback.data.split(":", 1)[1])
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.llm.pipeline.keyholder import evaluate_keyholder_action
        from app.services.llm_provider import get_active_llm_config

        async with async_session_factory() as db:
            llm_config = await get_active_llm_config(db, user.id)
            if not llm_config:
                await callback.answer("LLM provider config required for AI Keyholder.", show_alert=True)
                return

            eval_res = await evaluate_keyholder_action(
                db=db,
                user_id=user.id,
                session_id=session_id,
                action_type="extension_request",
                user_note="Requested via Telegram Bot",
                llm_config=llm_config,
                locale=user.locale or "ru",
            )

        decision = eval_res.get("decision", "rejected").upper()
        reason = eval_res.get("reasoning", "Action processed.")
        lines = [
            f"🤖 *AI Keyholder Verdict: {decision}*",
            f"📝 *Reasoning*: {reason}",
        ]
        if eval_res.get("extension_minutes"):
            lines.append(f"⏳ *Extension*: +{eval_res['extension_minutes']} minutes")

        await callback.message.answer("\n".join(lines), parse_mode="Markdown")
        await callback.answer("Keyholder evaluation complete.")

    @main_router.message(Command("aftercare"))
    async def cmd_aftercare(message: types.Message):
        """Generates step-by-step Aftercare guidance."""
        user = await _require_user(message)
        if user is None:
            return

        from app.llm.pipeline.aftercare import generate_aftercare_guidance
        from app.services.llm_provider import get_active_llm_config

        async with async_session_factory() as db:
            llm_config = await get_active_llm_config(db, user.id)
            if not llm_config:
                await message.answer("LLM provider config required for Aftercare AI.")
                return

            res = await generate_aftercare_guidance(
                db=db,
                user_id=user.id,
                llm_config=llm_config,
                locale=user.locale or "ru",
            )

        steps = res.get("aftercare_steps", [])
        lines = [
            "🧴 *Personalized Aftercare Protocol*",
            f"Summary: {res.get('summary', 'Rest and hydration.')}",
            "",
            "*Recommended Steps:*",
        ]
        for idx, step in enumerate(steps, 1):
            lines.append(f"{idx}. {step}")

        await message.answer("\n".join(lines), parse_mode="Markdown")

    @main_router.callback_query(F.data == "aftercare_gen")
    async def inline_aftercare_gen(callback: types.CallbackQuery):
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        from app.llm.pipeline.aftercare import generate_aftercare_guidance
        from app.services.llm_provider import get_active_llm_config

        async with async_session_factory() as db:
            llm_config = await get_active_llm_config(db, user.id)
            if not llm_config:
                await callback.answer("LLM provider required.", show_alert=True)
                return

            res = await generate_aftercare_guidance(
                db=db,
                user_id=user.id,
                llm_config=llm_config,
                locale=user.locale or "ru",
            )

        steps = res.get("aftercare_steps", [])
        lines = ["🧴 *Aftercare Plan:*"]
        for idx, step in enumerate(steps, 1):
            lines.append(f"{idx}. {step}")

        await callback.message.answer("\n".join(lines), parse_mode="Markdown")
        await callback.answer("Aftercare protocol generated.")

    @main_router.message(Command("report"))
    async def cmd_report(message: types.Message):
        """Generates a 1-Click Medical & Personal Summary Report."""
        user = await _require_user(message)
        if user is None:
            return

        from app.llm.pipeline.persona import generate_personal_medical_report

        async with async_session_factory() as db:
            rep = await generate_personal_medical_report(db, user.id, days=30)

        await message.answer(rep["report_markdown"], parse_mode="Markdown")


# ── Webhook endpoint ───────────────────────────────────────────────


@tg_router.post("/webhook")
async def tg_webhook(request: Request):
    """Receive Telegram updates via webhook."""
    if dp is None or bot is None:
        return {"status": "bot not configured"}

    # Verify secret token
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != TG_WEBHOOK_SECRET:
        return {"status": "unauthorized"}

    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")

    return {"status": "ok"}


# ── Polling mode (local dev) ───────────────────────────────────────

_polling_task: "asyncio.Task | None" = None


async def start_polling() -> None:
    """Start long-polling for local development. Runs as a background task."""
    global _polling_task
    if bot is None or dp is None:
        logger.warning("Polling requested but bot not configured (missing tg_bot_token)")
        return

    # Delete any existing webhook to avoid conflicts
    await bot.delete_webhook(drop_pending_updates=True)

    _polling_task = asyncio.create_task(dp.start_polling(bot))
    logger.info("Telegram polling started (local dev mode)")


async def stop_polling() -> None:
    """Stop polling gracefully."""
    global _polling_task
    if _polling_task:
        _polling_task.cancel()
        with contextlib.suppress(Exception):
            await _polling_task
        _polling_task = None
        logger.info("Telegram polling stopped")


# ── Set webhook on startup ─────────────────────────────────────────


async def setup_webhook(base_url: str) -> str | None:
    """Register the webhook URL with Telegram. Called at app startup."""
    if bot is None:
        return None
    webhook_url = f"{base_url.rstrip('/')}{TG_WEBHOOK_PATH}"
    try:
        await bot.set_webhook(
            url=webhook_url,
            secret_token=TG_WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
        logger.info(f"Telegram webhook set to {webhook_url}")
        return webhook_url
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook: {e}")
        return None
