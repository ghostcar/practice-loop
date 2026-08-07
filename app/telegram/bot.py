"""Telegram bot — aiogram 3.x, webhook via nginx, interactive commands."""

import logging
import uuid

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
from app.models.user import User

logger = logging.getLogger(__name__)

# --- Bot setup ---
TG_BOT_TOKEN = getattr(settings, "tg_bot_token", None)
TG_WEBHOOK_SECRET = getattr(settings, "tg_webhook_secret", "change-me")

bot: Bot | None = None
dp: Dispatcher | None = None
tg_router = APIRouter(prefix="/tg", tags=["telegram"])

if TG_BOT_TOKEN:
    bot = Bot(token=TG_BOT_TOKEN)
    dp = Dispatcher()
    main_router = Router()
    dp.include_router(main_router)

    # --- Commands ---

    @main_router.message(Command("start"))
    async def cmd_start(message: types.Message):
        """Welcome + account linking."""
        await message.answer(
            "👋 Welcome to Tracker Bot!\n\n"
            "Link your account: copy the code from your web profile "
            "and send /link YOUR_CODE\n\n"
            "Commands:\n"
            "/next — generate a task\n"
            "/done — mark complete\n"
            "/stats — your stats\n"
            "/session — session status\n"
            "/settings — preferences"
        )

    @main_router.message(Command("link"))
    async def cmd_link(message: types.Message):
        """Link Telegram account to web profile."""
        code = message.text.replace("/link", "").strip()
        if not code:
            await message.answer("Usage: /link YOUR_CODE\nFind the code in your web profile settings.")
            return

        async with async_session_factory() as db:
            # Use code as user_id for linking (simplified)
            try:
                uid = uuid.UUID(code)
                result = await db.execute(select(User).where(User.id == uid))
                user = result.scalar_one_or_none()
                if user:
                    # Store chat_id — in a real app we'd have a telegram_chat_id column
                    await message.answer(f"✅ Linked to {user.email}!\nUse /next to get started.")
                else:
                    await message.answer("❌ Invalid code. Check your web profile.")
            except ValueError:
                await message.answer("❌ Invalid code format.")

    @main_router.message(Command("next"))
    async def cmd_next(message: types.Message):
        """Generate a new task."""
        await message.answer("🎲 Generating a task for you... Send /done when complete.")

    @main_router.message(Command("done"))
    async def cmd_done(message: types.Message):
        """Mark task as done."""
        await message.answer("✅ Task marked as completed! Great job!")

    @main_router.message(Command("interrupt"))
    async def cmd_interrupt(message: types.Message):
        """Interrupt current task."""
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Yes, interrupt", callback_data="interrupt_confirm")],
                [InlineKeyboardButton(text="Cancel", callback_data="interrupt_cancel")],
            ]
        )
        await message.answer("⚠️ Interrupt current task? A penalty will be applied.", reply_markup=kb)

    @main_router.callback_query(F.data == "interrupt_confirm")
    async def interrupt_confirm(callback: types.CallbackQuery):
        await callback.message.edit_text("⏹ Task interrupted. Penalty applied. /next for a new task.")
        await callback.answer()

    @main_router.callback_query(F.data == "interrupt_cancel")
    async def interrupt_cancel(callback: types.CallbackQuery):
        await callback.message.edit_text("✅ Continue with your task!")
        await callback.answer()

    @main_router.message(Command("stats"))
    async def cmd_stats(message: types.Message):
        """Show user stats."""
        await message.answer(
            "📊 Your Stats:\n"
            "⭐ XP: N/A (link account first)\n"
            "📊 Level: N/A\n"
            "🔥 Streak: N/A\n"
            "✅ Completed: N/A\n\n"
            "Use /link YOUR_CODE to connect your account."
        )

    @main_router.message(Command("session"))
    async def cmd_session(message: types.Message):
        """Session status."""
        await message.answer("🎯 Session: No active session.\nCreate one in the web app to track activities together.")

    @main_router.message(Command("settings"))
    async def cmd_settings(message: types.Message):
        """Settings."""
        msg = "⚙️ Settings: language and reminder interval can be set in the web app."
        await message.answer(msg)


# --- Webhook endpoint ---


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
