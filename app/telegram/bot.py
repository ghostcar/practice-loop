"""Telegram bot — aiogram 3.x, webhook/polling, real task generation & gamification."""

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, datetime

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

            if user.telegram_link_code_expires and user.telegram_link_code_expires < datetime.now(UTC):
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
                    ActivityLog.status == "pending",
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
                    ActivityLog.status == "pending",
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
                    ActivityLog.status == "pending",
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
            if log.status != "pending":  # State integrity: no reward after interrupt/complete
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
            if log.status != "pending":  # State integrity: no re-interrupt of finished tasks
                await callback.answer("Task already finished.", show_alert=True)
                return

            log.status = "interrupted"
            db.add(log)
            await db.flush()
            penalty = await on_task_interrupted(db, user.id, log)
            await db.commit()

        name = log.selected_entity_name or "Task"
        lines = [
            f"⏹ **{name}** — interrupted",
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

    @main_router.message(Command("settings"))
    async def cmd_settings(message: types.Message):
        user = await _require_user(message)
        if user is None:
            return

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="EN 🇬🇧", callback_data="lang:en"),
                    InlineKeyboardButton(text="RU 🇷🇺", callback_data="lang:ru"),
                ]
            ]
        )
        await message.answer(
            f"⚙️ **Settings**\nLanguage: {user.locale.upper()}\n\nChange language:",
            parse_mode="Markdown",
            reply_markup=kb,
        )

    @main_router.callback_query(F.data.startswith("lang:"))
    async def inline_lang(callback: types.CallbackQuery):
        new_locale = callback.data.split(":", 1)[1]
        user = await _get_user_by_chat(callback.message.chat.id)
        if user is None:
            await callback.answer("Account not linked.", show_alert=True)
            return

        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.id == user.id))
            u = result.scalar_one_or_none()
            if u:
                u.locale = new_locale
                db.add(u)
                await db.commit()

        await callback.message.edit_text(f"⚙️ Language set to: {new_locale.upper()}")
        await callback.answer()


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
